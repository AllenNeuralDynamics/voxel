import json
import math
import queue
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import psutil
from matplotlib import pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.gridspec import GridSpec

from voxel.acquisition.planner import AcquisitionPlan
from voxel.channel import VoxelChannel
from voxel.daq.tasks.wavegen.wavegen_task import WaveGenTask
from voxel.devices.linear_axis import ScanConfig
from voxel.instrument import VoxelInstrument
from voxel.utils.log_config import get_logger

if TYPE_CHECKING:
    from matplotlib.image import AxesImage
    from matplotlib.text import Text

    from voxel.daq.tasks.clockgen import ClockGenTask
    from voxel.frame_stack import FrameStack


def get_available_disk_space_mb(path: str) -> int:
    """Return the available disk space in mega bytes."""
    return psutil.disk_usage(path).free // (1024**2)


def calculate_frame_stack_size_mb(frame_stack: "FrameStack", channel: VoxelChannel) -> float:
    pixel_count = frame_stack.size_um.x * frame_stack.size_um.y
    frame_size_bytes = pixel_count * np.dtype(channel.writer.dtype).itemsize
    return frame_size_bytes / (1024**2)


def display_frame_with_metadata0(frame: np.ndarray, stack_idx: str, channel: str, metadata: dict | None = None):
    plt.imshow(frame, cmap="gray")  # Display the frame in grayscale
    title = f"Stack: {stack_idx}, Channel: {channel}"

    # Add additional metadata to the title if provided
    if metadata:
        metadata_str = "| ".join(f"{key}: {value}" for key, value in metadata.items())
        title += f"\n{metadata_str}"

    plt.title(title, fontsize=10)
    plt.axis("off")  # Hide axis for better visualization
    plt.show(block=False)  # Non-blocking show for real-time updates
    plt.pause(0.1)  # Pause to allow update
    plt.clf()  # Clear the figure for the next frame


class FrameVisualizers:
    def __init__(self):
        # Initialize a persistent figure and axes
        self.fig = plt.figure(figsize=(10, 5))  # Wider figure to accommodate the metadata
        self.gs = GridSpec(1, 2, width_ratios=[3, 1])  # Allocate 3:1 space for the frame and metadata
        self.ax_frame = self.fig.add_subplot(self.gs[0])
        self.ax_metadata = self.fig.add_subplot(self.gs[1])
        self.initialized = False

    def display_frame(self, frame: np.ndarray, stack_idx: str, channel: str, metadata: dict | None = None):
        """
        Displays a frame with metadata in a persistent, auto-updating plot.

        :param frame: (np.ndarray): The frame to display.
        :param stack_idx: (str): Identifier for the current stack.
        :param channel: (str): Name of the current channel.
        :param metadata: (dict, optional): Additional metadata to display.
        """
        # Clear previous content for fresh updates
        if not self.initialized:
            self.fig.suptitle("Frame Visualization", fontsize=14)
            self.initialized = True

        self.ax_frame.clear()
        self.ax_metadata.clear()

        # Prepare metadata text
        metadata_lines = [f"Stack: {stack_idx}", f"Channel: {channel}"]
        if metadata:
            metadata_lines.extend(f"{key}: {value}" for key, value in metadata.items())
        metadata_text = "\n".join(metadata_lines)

        # Update the frame section
        self.ax_frame.imshow(frame, cmap="gray")
        self.ax_frame.axis("off")  # No axis for the frame

        # Update the metadata section
        self.ax_metadata.axis("off")  # No axis for the metadata text
        self.ax_metadata.text(
            0.01,
            1,  # Start from top-left corner
            metadata_text,
            fontsize=10,
            verticalalignment="top",
            horizontalalignment="left",
            transform=self.ax_metadata.transAxes,  # Use axis coordinates for positioning
        )

        # Redraw the figure without blocking
        plt.pause(0.1)


class FrameVisualizer:
    def __init__(self):
        self.frame_queue = queue.Queue()
        self.stop_event = threading.Event()

        # Initialize the figure
        self.fig = plt.figure(figsize=(10, 5))
        self.gs = GridSpec(1, 2, width_ratios=[3, 1])
        self.ax_frame = self.fig.add_subplot(self.gs[0])
        self.ax_metadata = self.fig.add_subplot(self.gs[1])
        self.fig.suptitle("Frame Visualization", fontsize=14)

        # Placeholders for frame and metadata
        self.current_frame = None
        self.current_metadata = None

        # Start FuncAnimation for updates
        self.ani = FuncAnimation(self.fig, self._update_plot, interval=100, cache_frame_data=False)

    def display_frame(self, frame, stack_idx, channel, metadata):
        """Add a frame and metadata to the queue."""
        self.frame_queue.put((frame, stack_idx, channel, metadata))

    def _update_plot(self, frame) -> list:
        """Update the plot by fetching new data from the queue."""
        artists = []  # Collect artists to return
        if not self.frame_queue.empty():
            self.current_frame, stack_idx, channel, metadata = self.frame_queue.get()

            # Clear previous content
            self.ax_frame.clear()
            self.ax_metadata.clear()

            # Update frame
            img: AxesImage = self.ax_frame.imshow(self.current_frame, cmap="gray")
            self.ax_frame.axis("off")
            artists.append(img)

            # Update metadata
            metadata_text = f"Stack: {stack_idx}\nChannel: {channel}"
            if metadata:
                metadata_text += "\n" + "\n".join(f"{k}: {v}" for k, v in metadata.items())

            text: Text = self.ax_metadata.text(
                0.01, 1, metadata_text, fontsize=10, verticalalignment="top", transform=self.ax_metadata.transAxes
            )
            self.ax_metadata.axis("off")
            artists.append(text)

        return artists  # Return the list of updated Artists

    def start(self):
        """Start the matplotlib main loop."""
        plt.show()

    def stop(self):
        """Stop the visualization."""
        self.stop_event.set()


class VoxelAcquisitionEngine(ABC):
    def __init__(
        self,
        instrument: VoxelInstrument,
        plan: AcquisitionPlan,
        path: str | Path,
    ) -> None:
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
        """Validate the acquisition plan.
        - Check that the scan path is valid
        - Check that the position of the frame_stacks is within the limits of the stage
        """
        if len(self.plan.scan_path) != len(self.plan.frame_stacks):
            self.log.warning("Scan path does not include all frame stacks.")
        errors = []
        errors.extend(self._validate_frame_stack_positions())
        if errors:
            for error in errors:
                self.log.error(error)
            raise ValueError("Invalid acquisition plan.")

    def _validate_frame_stack_positions(self) -> list[str]:
        """Ensure frame stack positions are within stage limits."""
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


@dataclass
class StackAcquisitionState:
    frame_counter: int = 0
    avg_write_speed_mb_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "frame_counter": self.frame_counter,
            "avg_write_speed_mb_s": f"{self.avg_write_speed_mb_s:.2f} MB/s",
        }


class ExaspimAcquisitionEngine(VoxelAcquisitionEngine):
    def __init__(
        self,
        instrument: VoxelInstrument,
        plan: AcquisitionPlan,
        path: str | Path,
    ) -> None:
        super().__init__(instrument=instrument, plan=plan, path=path)

        if not self.instrument.daq:
            raise ValueError("DAQ not found in the instrument.")

        acq_task = self.instrument.daq.tasks.get("acq_task")
        if not isinstance(acq_task, WaveGenTask):
            raise ValueError("Acquisition task not found or is not a WaveGenTask.")

        self.acq_task: WaveGenTask = acq_task
        self.log.debug(f"Acquistion task found with channels: {self.acq_task.channels.keys()}")

        clock_task = self.acq_task.trigger_task
        if not clock_task:
            raise ValueError("Trigger Clock task not found in acquisition task.")
        self.clock_task: "ClockGenTask" = clock_task

        self.state = {
            stack.idx: {channel.name: StackAcquisitionState() for channel in self.channels}
            for stack in self.plan.frame_stacks.values()
        }

        self.current_stack: FrameStack

        self.visualizer = FrameVisualizer()

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
        acquisition_thread = threading.Thread(target=self._acquisition_loop)
        acquisition_thread.start()

        try:
            self.visualizer.start()  # Start the main Matplotlib loop
        finally:
            acquisition_thread.join()
            self.visualizer.stop()
            self.log.info(f"Acquisition complete. State: {self.state_str}")

    def _acquisition_loop(self):
        """Background acquisition process."""
        for tile_idx in self.plan.scan_path:
            self._capture_stack(self.plan.frame_stacks[tile_idx])

    def _capture_stack(self, stack: "FrameStack") -> None:
        """Capture a frame stack."""
        self.log.info(f"Capturing frame stack: {stack.idx}")

        self.acq_task.regenerate_waveforms()
        self.acq_task.write()
        self.acq_task.start()

        for i, channel in enumerate(self.channels):
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

            self.clock_task.freq_hz = 1000 / channel.camera.frame_time_ms
            self.log.info(f"Clock frequency set to: {self.clock_task.freq_hz:.2f} Hz")

            expected_size_mb = calculate_frame_stack_size_mb(stack, channel)

            while not self.available_disk_space > expected_size_mb * 1.5:
                self.log.warning("Low disk space. Waiting for space to free up.")
                time.sleep(5)

            channel.activate()

            channel.prepare(stack=stack, channel_idx=i, path=self.path)

            batch_size = channel.writer.batch_size_px
            self.clock_task.configure(num_samples=batch_size)

            num_batches = math.ceil(stack.frame_count / batch_size)

            batches_range = range(1, num_batches + 1)

            channel.writer.start()

            for batch_idx in batches_range:
                start_idx = relevant_state.frame_counter + 1
                frame_range = range(start_idx, min(start_idx + batch_size, stack.frame_count + 1))

                if batch_idx == len(batches_range):
                    # self.clock_task.configure(num_samples=stack.frame_count % batch_size or batch_size)
                    self.clock_task.configure(num_samples=len(frame_range))

                self.log.info(f"Batch {batch_idx}/{num_batches} [{range_str(frame_range)}] = {len(frame_range)}")

                self.clock_task.start()
                channel.camera.start(frame_count=len(frame_range))
                for i in frame_range:
                    start_time = time.perf_counter()
                    channel.capture_frame()
                    end_time = time.perf_counter()

                    relevant_state.frame_counter += 1
                    if i == frame_range[-1]:
                        self.log.info(f"Captured frame {i} - {1 / (end_time - start_time):.2f} fps")
                        self.log.info(f"Camera state: {channel.camera.acquisition_state}")

                    if channel.latest_frame is not None:
                        self.visualizer.display_frame(
                            frame=channel.latest_frame,
                            stack_idx=stack.idx.to_str(),
                            channel=channel.name,
                            metadata={
                                "Frame idx": relevant_state.frame_counter,
                                "Capture Fps": f"{1 / (end_time - start_time):.2f}",
                                "Avg write fps": f"{channel.writer.avg_write_speed_fps:.2f}",
                                "Avg write speed": f"{channel.writer.avg_write_speed_mb_s:.2f} MB/s",
                            },
                        )
                channel.camera.stop()
                self.clock_task.stop()

            relevant_state.avg_write_speed_mb_s = channel.writer.avg_write_speed_mb_s

            self.log.info(f"Camera qcquisition state: {channel.camera.acquisition_state}")

            channel.writer.close()
            channel.deactivate()

        self.acq_task.stop()


def range_str(rng: range) -> str:
    # Convert a range object to a string e.g. "1-10" where rng = range(1, 11)
    return f"{rng.start}-{rng.stop - 1}"
