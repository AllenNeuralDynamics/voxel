import json
import math
import time
import threading
import queue
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import psutil
from voxel.acquisition.planner import AcquisitionPlan
from voxel.channel import VoxelChannel
from voxel.daq.tasks.wavegen import WaveGenTask
from voxel.devices.linear_axis import ScanConfig
from voxel.instrument import VoxelInstrument
from voxel.utils.log_config import get_logger

if TYPE_CHECKING:
    from voxel.daq.tasks.clockgen import ClockGenTask
    from voxel.frame_stack import FrameStack


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
    avg_write_speed_mb_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "frame_counter": self.frame_counter,
            "avg_write_speed_mb_s": f"{self.avg_write_speed_mb_s:.2f} MB/s",
        }


class VoxelAcquisitionEngine(ABC):
    def __init__(self, instrument: VoxelInstrument, plan: AcquisitionPlan, path: str | Path) -> None:
        self.log = get_logger(self.__class__.__name__)
        self.instrument = instrument
        self.stage = self.instrument.stage
        self.channels = [instrument.channels[channel_name] for channel_name in plan.channels]
        self.plan = plan
        self.path = Path(path)
        self.validate_acquisition_plan()

    @property
    def available_disk_space(self) -> int:
        return get_available_disk_space_mb(str(self.path))

    @abstractmethod
    def run(self) -> None: ...

    def validate_acquisition_plan(self):
        if len(self.plan.scan_path) != len(self.plan.frame_stacks):
            self.log.warning("Scan path does not include all frame stacks.")
        errors = self._validate_frame_stack_positions()
        if errors:
            for error in errors:
                self.log.error(error)
            raise ValueError("Invalid acquisition plan.")

    def _validate_frame_stack_positions(self) -> list[str]:
        errors = []
        min_limit, max_limit = self.stage.limits_mm
        for stack in self.plan.frame_stacks.values():
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
    def __init__(self, instrument: VoxelInstrument, plan: AcquisitionPlan, path: str | Path):
        super().__init__(instrument, plan, path)
        self.frame_queue = queue.Queue()
        if not self.instrument.daq:
            raise ValueError("DAQ not found in the instrument.")

        acq_task = self.instrument.daq.tasks.get("acq_task")
        if not isinstance(acq_task, WaveGenTask):
            raise ValueError("Acquisition task not found or is not a WaveGenTask.")

        self.acq_task: WaveGenTask = acq_task

        clock_task = self.acq_task.trigger_task
        if not clock_task:
            raise ValueError("Trigger Clock task not found in acquisition task.")
        self.clock_task: "ClockGenTask" = clock_task

        self.state = {
            stack.idx: {channel.name: StackAcquisitionState() for channel in self.channels}
            for stack in self.plan.frame_stacks.values()
        }

        self._stop_event = threading.Event()

    @property
    def state_str(self) -> str:
        return json.dumps(
            {
                stack_idx.to_str(): {channel: state.to_dict() for channel, state in states.items()}
                for stack_idx, states in self.state.items()
            },
            indent=2,
        )

    def run(self):
        self.log.info("Starting acquisition.")
        for tile_idx in self.plan.scan_path:
            if self._stop_event.is_set():
                break
            self._capture_stack(self.plan.frame_stacks[tile_idx])
        self.log.info(f"Acquisition complete. State: {self.state_str}")

    def stop(self):
        self._stop_event.set()

    def _capture_stack(self, stack: "FrameStack") -> None:
        self.log.info(f"Capturing frame stack: {stack.idx}")

        self.acq_task.regenerate_waveforms()
        self.acq_task.write()
        self.acq_task.start()

        for i, channel in enumerate(self.channels):
            if self._stop_event.is_set():
                break

            self.stage.move_to(x=stack.pos_um.x, y=stack.pos_um.y, z=stack.pos_um.z, wait=True)

            self.stage.z.configure_scan(
                ScanConfig(
                    scan_type=ScanConfig.ScanType.STEP_AND_SHOOT,
                    start_mm=stack.pos_um.z,
                    stop_mm=(stack.pos_um.z + stack.size_um.z),
                    step_size_um=stack.step_size_um,
                )
            )

            relevant_state = self.state[stack.idx][channel.name]

            # self.clock_task.freq_hz = (1000 / channel.camera.frame_time_ms) * 0.75
            self.clock_task.freq_hz = 1000 / channel.camera.frame_time_ms
            self.log.info(f"Clock frequency set to: {self.clock_task.freq_hz:.2f} Hz")

            expected_size_mb = calculate_frame_stack_size_mb(stack, channel)

            while not self.available_disk_space > expected_size_mb * 1.5 and not self._stop_event.is_set():
                self.log.warning("Low disk space. Waiting for space to free up.")
                time.sleep(1)

            if self._stop_event.is_set():
                break

            channel.activate()
            channel.prepare(stack=stack, channel_idx=i, path=self.path)

            batch_size = channel.writer.batch_size_px
            self.clock_task.configure(num_samples=batch_size)

            num_batches = math.ceil(stack.frame_count / batch_size)
            batches_range = range(1, num_batches + 1)

            channel.writer.start()

            for batch_idx in batches_range:
                if self._stop_event.is_set():
                    break

                start_idx = relevant_state.frame_counter + 1
                frame_range = range(start_idx, min(start_idx + batch_size, stack.frame_count + 1))

                if batch_idx == len(batches_range):
                    self.clock_task.configure(num_samples=len(frame_range))

                self.log.info(f"Batch {batch_idx}/{num_batches} [{range_str(frame_range)}] = {len(frame_range)}")

                channel.camera.start(frame_count=len(frame_range))
                self.clock_task.start()
                for frame_idx in frame_range:
                    if self._stop_event.is_set():
                        break

                    start_time = time.perf_counter()
                    channel.capture_frame()
                    end_time = time.perf_counter()

                    relevant_state.frame_counter += 1
                    if frame_idx == frame_range[-1]:
                        self.log.info(f"Captured frame {frame_idx} - {1 / (end_time - start_time):.2f} fps")
                        self.log.info(f"Camera state: {channel.camera.acquisition_state}")

                    if channel.latest_frame is not None:
                        metadata = {
                            "stack idx": stack.idx.to_str(),
                            "Channel": channel.name,
                            "Frame idx": relevant_state.frame_counter,
                            "Capture Fps": f"{1 / (end_time - start_time):.2f}",
                            "Avg write fps": f"{channel.writer.avg_write_speed_fps:.2f}",
                            "Avg write speed": f"{channel.writer.avg_write_speed_mb_s:.2f} MB/s",
                        }
                        # Put the frame and metadata in the queue for visualization
                        self.frame_queue.put((channel.latest_frame, metadata))

                channel.camera.stop()
                self.clock_task.stop()

            relevant_state.avg_write_speed_mb_s = channel.writer.avg_write_speed_mb_s
            self.log.info(f"Camera acquisition state: {channel.camera.acquisition_state}")

            channel.writer.close()
            channel.deactivate()

        self.acq_task.stop()


def range_str(rng: range) -> str:
    return f"{rng.start}-{rng.stop - 1}"
