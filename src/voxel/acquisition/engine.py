from dataclasses import dataclass
from abc import ABC, abstractmethod
import math
from pathlib import Path
import time

import numpy as np
from voxel.channel import VoxelChannel
from voxel.daq.tasks.wavegen.wavegen_task import WaveGenTask
from voxel.devices.linear_axis import ScanConfig
from voxel.instrument import VoxelInstrument
from voxel.utils.vec import Vec2D
from voxel.utils.log_config import get_logger
import psutil

from typing import TYPE_CHECKING
from voxel.frame_stack import FrameStack

if TYPE_CHECKING:
    from voxel.daq.tasks.clockgen import ClockGenTask

    pass


@dataclass
class AcquisitionState:
    progress: dict[Vec2D, list[float]]


def get_available_disk_space_mb(path: str) -> int:
    """Return the available disk space in mega bytes."""
    return psutil.disk_usage(path).free // (1024**2)


def calculate_frame_stack_size_mb(frame_stack: "FrameStack", channel: VoxelChannel) -> float:
    pixel_count = frame_stack.size_um.x * frame_stack.size_um.y
    frame_size_bytes = pixel_count * np.dtype(channel.writer.dtype).itemsize
    return frame_size_bytes / (1024**2)


@dataclass
class StackAcquisitionState:
    frame_counter: int = 0
    latest_frame: np.ndarray | None = None

    def new_frame(self, frame: np.ndarray | None) -> None:
        if frame is not None:
            self.latest_frame = frame
            self.frame_counter += 1


class VoxelAcquisitionEngine(ABC):
    def __init__(
        self,
        instrument: VoxelInstrument,
        channels: list[str],
        frame_stacks: dict[Vec2D, FrameStack],
        scan_path: list[Vec2D[int]],
        path: str | Path,
    ) -> None:
        self.log = get_logger(self.__class__.__name__)

        self.instrument = instrument
        self.stage = self.instrument.stage
        self.channels = [instrument.channels[channel_name] for channel_name in channels]
        self.frame_stacks = frame_stacks
        self.scan_path = scan_path
        self.path = Path(path)

        self.validate_acquisition_plan()

    @property
    def available_disk_space(self) -> int:
        return get_available_disk_space_mb(str(self.path))

    @abstractmethod
    def run(self) -> None: ...

    def validate_acquisition_plan(self):
        """Validate the acquisition plan.
        - Check that the scan path is valid
        - Check that the position of the frame_stacks is within the limits of the stage
        """
        errors = []
        errors.extend(self._validate_scan_path())
        errors.extend(self._validate_frame_stack_positions())
        if len(self.scan_path) != len(self.frame_stacks):
            self.log.warning("Scan path does not include all frame stacks.")
        if errors:
            for error in errors:
                self.log.error(error)
            raise ValueError("Invalid acquisition plan.")

    def _validate_scan_path(self) -> list[str]:
        """Make sure the scan plan is valid."""
        errors = []
        for tile_idx in self.scan_path:
            if tile_idx not in self.frame_stacks:
                errors.append(f"Frame stack not found for tile index: {tile_idx}")
        return errors

    def _validate_frame_stack_positions(self) -> list[str]:
        """Ensure frame stack positions are within stage limits."""
        errors = []
        min_limit, max_limit = self.stage.limits_mm
        for stack in self.frame_stacks.values():
            min_corner = stack.pos_um
            max_corner = stack.pos_um + stack.size_um
            for coord in ["x", "y", "z"]:
                min_val = getattr(min_limit, coord)
                max_val = getattr(max_limit, coord)
                min_c = getattr(min_corner, coord)
                max_c = getattr(max_corner, coord)
                if not min_val <= min_c <= max_val:
                    errors.append(f"{coord.upper()} position of frame stack {stack.idx} is out of stage limits.")
                if not min_val <= max_c <= max_val:
                    errors.append(f"{coord.upper()} position of frame stack {stack.idx} is out of stage limits.")
        return errors


class ExaspimAcquisitionEngine(VoxelAcquisitionEngine):
    def __init__(
        self,
        instrument: VoxelInstrument,
        channels: list[str],
        frame_stacks: dict[Vec2D, FrameStack],
        scan_path: list[Vec2D[int]],
        path: str | Path,
    ) -> None:
        super().__init__(instrument, channels, frame_stacks, scan_path, path)

        if not self.instrument.daq:
            raise ValueError("DAQ not found in the instrument.")

        acq_task = self.instrument.daq.tasks.get("acq_task")
        if not isinstance(acq_task, WaveGenTask):
            raise ValueError("Acquisition task not found or is not a WaveGenTask.")

        self.acq_task: WaveGenTask = acq_task
        self.log.info(f"Acquistion task found with channels: {self.acq_task.channels.keys()}")

        clock_task = self.acq_task.trigger_task
        if not clock_task:
            raise ValueError("Trigger Clock task not found in acquisition task.")
        self.clock_task: "ClockGenTask" = clock_task

        self.state = {stack.idx: StackAcquisitionState() for stack in self.frame_stacks.values()}

        self.current_stack: FrameStack

    def run(self) -> None:
        for tile_idx in self.scan_path:
            self._capture_stack(self.frame_stacks[tile_idx])

    def _capture_stack(self, stack: "FrameStack") -> None:
        """Capture a frame stack."""
        self.log.warning(f"Capturing frame stack: {stack}")

        self.stage.move_to(x=stack.pos_um.x, y=stack.pos_um.y, z=stack.pos_um.z, wait=True)
        self.log.info(f"Moved to position: {self.stage.position_mm.to_str()}")

        self.stage.z.configure_scan(
            ScanConfig(
                scan_type=ScanConfig.ScanType.STEP_AND_SHOOT,
                start_mm=stack.pos_um.z,
                stop_mm=(stack.pos_um.z + stack.size_um.z),
                step_size_um=stack.step_size_um,
            )
        )

        self.acq_task.regenerate_waveforms()
        self.acq_task.write()
        self.acq_task.start()

        for i, channel in enumerate(self.channels):
            self.log.info(f"Capturing frames for channel: {channel.name}")

            self.clock_task.freq_hz = 1 / (channel.camera.frame_time_ms / 1000)
            acq_frame_time_s = (1 / self.clock_task.freq_hz) * 1
            self.log.info(
                f"Clock frequency set to: {self.clock_task.freq_hz:.2f} Hz, frame time: {acq_frame_time_s:.2f} s"
            )

            expected_size_mb = calculate_frame_stack_size_mb(stack, channel)

            while not self.available_disk_space > expected_size_mb * 1.5:
                self.log.warning("Low disk space. Waiting for space to free up.")
                time.sleep(5)

            channel.activate()
            channel.prepare(stack=stack, channel_idx=i, path=self.path)

            batch_size = channel.writer.batch_size_px
            self.clock_task.configure(num_samples=batch_size)

            num_batches = math.ceil(stack.frame_count / batch_size)

            channel.camera.start(frame_count=batch_size)
            channel.writer.start()

            channel.start(frame_count=batch_size)

            for batch_idx in range(num_batches):
                if batch_idx == num_batches - 1:
                    self.clock_task.configure(num_samples=stack.frame_count % batch_size or batch_size)
                self.clock_task.start()

                frame_range = range(
                    self.state[stack.idx].frame_counter,
                    min(self.state[stack.idx].frame_counter + batch_size, stack.frame_count),
                )
                self.log.info(f"  Batch {batch_idx + 1} of {num_batches} [{frame_range.start}-{frame_range.stop}]")

                for stack_index in frame_range:
                    start_time = time.perf_counter()
                    channel.capture_frame()
                    self.log.info(f"    Captured Frame {stack_index} of {stack.frame_count}")
                    self.state[stack.idx].new_frame(channel.latest_frame)

                    end_time = time.perf_counter()
                    if end_time - start_time < acq_frame_time_s:
                        time.sleep(acq_frame_time_s - (end_time - start_time))

                self.clock_task.stop()
                self.log.info(f"  Batch {batch_idx + 1} done")

            # channel.stop()
            channel.camera.stop()
            channel.deactivate()

        self.acq_task.stop()
