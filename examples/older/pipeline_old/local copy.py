from enum import StrEnum
import math
from pathlib import Path
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np

from voxel.frame_stack import StackAcquisitionConfig
from voxel.utils.common import get_available_disk_space_mb
from voxel.utils.log_config import get_component_logger, get_logger
from voxel.utils.vec import Vec3D

from .interface import ICameraPipeline, PipelineStatus, StackAcquisitionConfig
from voxel.io.manager import IOManager
from voxel.io.transfers.base import VoxelFileTransfer
from voxel.io.writers.base import VoxelWriter, WriterConfig
from .preview import (
    NewFrameCallback,
    PreviewMetadata,
    PreviewFrame,
    PreviewSettings,
    PreviewConfig,
    PreviewManager,
)

if TYPE_CHECKING:
    from voxel.devices.interfaces.camera import VoxelCamera


@dataclass
class LocalCameraPipeline(ICameraPipeline):
    def __init__(self, camera: "VoxelCamera", io_manager: IOManager):
        self.log = get_component_logger(self)
        self._camera = camera
        self._io_manager = io_manager

        self._writer = self._io_manager.get_writer_instance(io_manager.available_writers[0])

        self._transfer = self._io_manager.get_transfer_instance(io_manager.available_transfers[0])

        self._state = PipelineStatus.INACTIVE
        self._disk_space_check_interval = 2  # seconds
        self._latest_frame: np.ndarray | None = None

        self._preview_settings = PreviewSettings()
        self._preview_transform = PreviewConfig()
        self._preview_thread: threading.Thread | None = None
        self._halt_event = threading.Event()
        self._transform_lock = threading.Lock()

    @property
    def available_writers(self) -> list[str]:
        return self._io_manager.available_writers

    @property
    def writer(self) -> VoxelWriter:
        return self._writer

    def set_writer(self, writer_name: str) -> None:
        """Set the writer to a new writer."""
        if writer_name not in self.available_writers:
            raise ValueError(f"Writer {writer_name} not found in available writers.")
        if self._state != PipelineStatus.INACTIVE:
            raise RuntimeError("Cannot change writer while engine is running.")
        self.log.info(f"Changing writer from {self._writer.name} to {writer_name}.")
        self._writer.close()
        try:
            self._writer = self._io_manager.get_writer_instance(writer_name)
        except ValueError as e:
            self.log.error(f"Error setting writer {writer_name}: {e}")
            return
        self.log.info(f"Writer set to {writer_name}.")

    @property
    def available_transfers(self) -> list[str]:
        return self._io_manager.available_transfers

    @property
    def transfer(self) -> VoxelFileTransfer | None:
        return self._transfer

    def set_transfer(self, transfer_name: str) -> None:
        """Set the transfer to a new transfer."""
        if transfer_name not in self.available_transfers:
            raise ValueError(f"Transfer {transfer_name} not found in available transfers.")
        if self._state != PipelineStatus.INACTIVE:
            raise RuntimeError("Cannot change transfer while pipeline is running.")
        self.log.info(f"Setting transfer to {transfer_name}.")
        try:
            self._transfer = self._io_manager.get_transfer_instance(transfer_name)
        except ValueError as e:
            self.log.error(f"Error setting transfer {transfer_name}: {e}")
            return
        self.log.info(f"Transfer set to {transfer_name}.")

    @property
    def camera(self) -> "VoxelCamera":
        return self._camera

    @property
    def state(self) -> PipelineStatus:
        return self._state

    @property
    def frame_pixel_count(self) -> int:
        return self.camera.frame_size_px.x * self.camera.frame_size_px.y

    @property
    def frame_size_mb(self) -> float:
        return self.frame_pixel_count * np.dtype(self._writer.dtype).itemsize / (1024**2)

    @property
    def frame_rate_hz(self) -> float:
        return self.camera.frame_rate_hz

    def update_preview_transform(self, transform: PreviewConfig) -> None:
        with self._transform_lock:
            self._preview_transform = transform

    def get_latest_preview(self) -> PreviewFrame | None:
        """Get the latest preview frame."""
        return self._generate_preview_frame(self._latest_frame) if self._latest_frame is not None else None

    def start_preview(self, on_new_frame: NewFrameCallback) -> None:
        """Start the preview mode."""
        self.log.info("Starting preview mode.")
        self.camera.prepare()
        self.camera.start()
        self._halt_event.clear()
        self._preview_thread = threading.Thread(target=self._preview_loop, args=(on_new_frame,), daemon=True)
        self._state = PipelineStatus.PREVIEWING
        self._preview_thread.start()

    def stop_preview(self) -> None:
        """Stop the preview mode."""
        self.log.info("Stopping preview mode.")
        self._halt_event.set()
        if self._preview_thread is not None:
            self._preview_thread.join()
            self._preview_thread = None
        self.camera.stop()
        self._state = PipelineStatus.INACTIVE

    def prepare_stack_acquisition(self, config: StackAcquisitionConfig) -> list[range]:
        """Prepare the engine for acquisition."""
        self.log.info("Preparing for stack acquisition.")
        self.camera.prepare()
        self._writer.configure(
            WriterConfig(
                frame_shape=self.camera.frame_size_px,
                voxel_size=Vec3D(
                    self.camera.pixel_size_um.x,
                    self.camera.pixel_size_um.y,
                    config.stack.step_size_um,
                ),
                path=config.local_path,
                frame_count=config.stack.frame_count,
                position_um=config.stack.pos_um,
                channel_name=config.channel_name,
                channel_idx=config.channel_idx,
                batch_size=128,
                file_name=f"tile_{config.stack.idx.x}_{config.stack.idx.y}_{config.channel_name}",
            )
        )
        self._writer.start()

        self._wait_for_disk_space(config.stack.frame_count)

        self._state = PipelineStatus.STACK_CONFIGURED

        return self._get_frame_ranges(config.stack.frame_count)

    def acquire_batch(self, frame_range: range, on_new_frame: NewFrameCallback) -> None:
        """Acquire a batch of frames given a range of frame indices."""
        self.log.info(f"Acquiring batch: {frame_range}")
        self.camera.start(frame_count=len(frame_range))  # prepare_batch, camera will wait for n hardware triggers
        for frame_idx in frame_range:
            if self._halt_event.is_set():
                break
            try:
                self._latest_frame = self.camera.grab_frame()
                self._handle_on_new_frame(frame=self._latest_frame, frame_idx=frame_idx, on_new_frame=on_new_frame)
                self._writer.add_frame(self._latest_frame)
            except Exception as e:
                self.log.error(f"Error during acquisition: {e}")
        self.camera.stop()

    def finalize_stack_acquisition(self) -> None:
        """Finalize the acquisition process."""
        self.log.info("Finalizing stack acquisition.")
        self._writer.close()
        self._state = PipelineStatus.INACTIVE

    def _wait_for_disk_space(self, frame_count: int) -> None:
        """Wait for sufficient disk space before starting acquisition."""
        while self.frame_size_mb * frame_count > get_available_disk_space_mb(str(self._writer.config.path)):
            self.log.warning("Low disk space. Waiting for space to free up.")
            time.sleep(self._disk_space_check_interval)

    def _get_frame_ranges(self, frame_count: int) -> list[range]:
        """Generate frame ranges for batch acquisition."""
        num_batches = math.ceil(frame_count / self._writer.batch_size_px)
        frame_ranges = []
        for i in range(num_batches):
            start_idx = i * self._writer.batch_size_px + 1
            end_idx = min(start_idx + self._writer.batch_size_px - 1, frame_count)
            frame_ranges.append(range(start_idx, end_idx + 1))
        return frame_ranges

    def _preview_loop(self, on_new_frame: NewFrameCallback) -> None:
        """Continuously capture preview frames and update self.latest_frame."""
        frame_idx = 0
        while not self._halt_event.is_set() and self._state == PipelineStatus.PREVIEWING:
            try:
                self._latest_frame = self.camera.grab_frame()
                self._handle_on_new_frame(frame=self._latest_frame, frame_idx=frame_idx, on_new_frame=on_new_frame)
                frame_idx += 1
            except Exception as e:
                self.log.error(f"Error capturing preview frame: {e}")
            time.sleep(self.camera.frame_time_ms * 0.25 / 1000)  # Sleep for 0.25 of the frame time

    def _handle_on_new_frame(self, frame: np.ndarray, frame_idx: int, on_new_frame: NewFrameCallback) -> None:
        on_new_frame(self._generate_preview_frame(raw_frame=frame, frame_idx=frame_idx))
        if self._preview_transform.k != 0.0:
            on_new_frame(self._generate_preview_frame(frame, frame_idx=frame_idx, transform=self._preview_transform))

    def _generate_preview_frame(
        self,
        raw_frame: np.ndarray,
        frame_idx: int = 0,
        transform: PreviewConfig | None = None,
    ) -> PreviewFrame:
        """
        Generate a PreviewFrame from the raw frame using the current preview_settings.
        The method crops the raw frame to the ROI (using normalized coordinates) and then
        resizes the cropped image to the target preview dimensions. It also applies black/white
        point and gamma adjustments to produce an 8-bit preview.
        """
        full_width = raw_frame.shape[1]
        full_height = raw_frame.shape[0]
        preview_width = self._preview_settings.width
        preview_height = int(full_height * (preview_width / full_width))

        # Build the metadata object (assuming PreviewMetadata supports these fields).
        config = PreviewMetadata(
            frame_idx=frame_idx,
            preview_width=preview_width,
            preview_height=preview_height,
            full_width=full_width,
            full_height=full_height,
            transform=transform or PreviewConfig(x=0.0, y=0.0, k=0.0),
            channel_name="<channel_name>",
        )

        # 1) Compute absolute ROI coordinates.
        if transform is not None:
            zoom = 1 - config.transform.k  # for k 0.0 is no zoom, 1.0 is full zoom
            roi_x0 = int(full_width * config.transform.x)
            roi_y0 = int(full_height * config.transform.y)
            roi_x1 = roi_x0 + int(full_width * zoom)
            roi_y1 = roi_y0 + int(full_height * zoom)

            # 2) Crop to the ROI.
            # 3) Resize to the target dimensions (still in the original dtype, e.g. uint16).
            raw_frame = raw_frame[roi_y0:roi_y1, roi_x0:roi_x1]

        preview_img = cv2.resize(raw_frame, (preview_width, preview_height), interpolation=cv2.INTER_AREA)

        # 4) Convert to float32 for intensity scaling.
        preview_float = preview_img.astype(np.float32)

        # 5) Determine the max possible value from the raw frame's dtype (e.g. 65535 for uint16).
        # 6) Compute the actual black/white values from percentages.
        # 7) Clamp to [black_val..white_val].
        max_val = np.iinfo(raw_frame.dtype).max
        black_val = config.correction.black * max_val
        white_val = config.correction.white * max_val
        preview_float = np.clip(preview_float, black_val, white_val)

        # 8) Normalize to [0..1].
        denom = (white_val - black_val) + 1e-8
        preview_float = (preview_float - black_val) / denom

        # 9) Apply gamma correction (gamma factor in PreviewSettings).
        #    If gamma=1.0, no change.
        if (g := config.correction.gamma) != 1.0:
            preview_float = preview_float ** (1.0 / g)

        # 10) Scale to [0..255] and convert to uint8.
        preview_float *= 255.0
        preview_uint8 = preview_float.astype(np.uint8)

        # 11) Return the final 8-bit preview.
        return PreviewFrame(frame=preview_uint8, metadata=config)


class StackAcquisitionRunner:
    def __init__(
        self,
        *,
        camera: "VoxelCamera",
        writer: VoxelWriter,
        config: StackAcquisitionConfig,
        preview_manager: PreviewManager,
        transfer: VoxelFileTransfer | None = None,
    ):
        self.log = get_logger(f"StackRunner.{config.channel_name}.{config.stack.idx.x}_{config.stack.idx.y}")
        self._camera = camera
        self._writer = writer
        self._transfer = transfer
        self._preview_manager = preview_manager

        self._batch_capture_thread: threading.Thread | None = None
        self._batch_completion_event = threading.Event()
        self._batch_halt_event = threading.Event()

        try:
            self._camera.prepare()
            self._writer.configure(
                WriterConfig(
                    frame_shape=self._camera.frame_size_px,
                    voxel_size=Vec3D(
                        self._camera.pixel_size_um.x,
                        self._camera.pixel_size_um.y,
                        config.stack.step_size_um,
                    ),
                    path=config.local_path,
                    batch_size=config.batch_size,
                    frame_count=config.stack.frame_count,
                    position_um=config.stack.pos_um,
                    channel_name=config.channel_name,
                    channel_idx=config.channel_idx,
                    file_name=f"tile_{config.stack.idx.x}_{config.stack.idx.y}_{config.channel_name}",
                )
            )
            self._wait_for_disk_space(self._writer.config.path)
            self._writer.start()

            self._target_frame_count = config.stack.frame_count
            self._captured_frames = 0
        except Exception as e:
            self.log.error(f"Error during stack acquisition preparation: {e}")
            self._writer.close()
            raise

    def is_active(self) -> bool:
        """Check if the acquisition runner is currently busy."""
        return self._batch_capture_thread is not None and self._batch_capture_thread.is_alive()

    def _wait_for_disk_space(self, path: str | Path) -> None:
        """Wait for sufficient disk space before starting acquisition."""
        frame_size_mb = self._camera.pixel_count * np.dtype(self._writer.dtype).itemsize / (1024**2)
        while frame_size_mb * self._target_frame_count > get_available_disk_space_mb(str(path)):
            self.log.warning("Low disk space. Waiting for space to free up.")
            time.sleep(2)

    def acquire_batch(self, start_idx: int, end_idx: int, start_trigger: threading.Event) -> threading.Event:
        """Acquire a batch of frames from start_idx to end_idx.
        - Calls camera.start() to prepare the camera for acquisition.
        - waits for the start event to begin the acquisition loop.
        - returns an event that signals when the batch acquisition is complete.
        """
        if self._batch_capture_thread is not None and self._batch_capture_thread.is_alive():
            raise RuntimeError("A batch capture thread is already running. Please wait for it to finish.")

        try:
            self._camera.start(frame_count=end_idx - start_idx + 1)
            self._batch_completion_event.clear()  # Reset the completion event
            self._batch_capture_thread = threading.Thread(
                target=self._batch_acquisition_loop_target,
                args=(
                    start_idx,
                    end_idx,
                    self._writer.config.channel_name,
                    start_trigger,
                    self._batch_completion_event,
                ),
                daemon=False,
                name=f"BatchAcquisitionThread-{start_idx}-{end_idx}",
            )
            self._batch_capture_thread.start()
            return self._batch_completion_event
        except Exception as e:
            self.log.error(f"Error starting batch acquisition: {e}")
            self._writer.close()
            raise

    def _batch_acquisition_loop_target(
        self,
        start_idx: int,
        end_idx: int,
        channel_name: str,
        start_trigger: threading.Event,
        completion_notifier: threading.Event,
    ) -> None:
        """
        Thread target: waits for the start_trigger event to begin acquisition.
        It will acquire frames from start_idx to end_idx, adding them to the writer and updating the preview manager.
        """
        start_signal_recieved = start_trigger.wait(timeout=60.0)  # Wait for the start signal for up to 60 seconds
        if not start_signal_recieved:
            self.log.error("Start signal not received within timeout. Aborting batch acquisition.")
            completion_notifier.set()
            return

        self.log.info(f"Starting batch acquisition from {start_idx} to {end_idx}.")
        for frame_idx in range(start_idx, end_idx + 1):
            if self._batch_halt_event.is_set():
                self.log.info("Batch acquisition halted by user.")
                break
            try:
                frame = self._camera.grab_frame()
                self._writer.add_frame(frame)
                self._preview_manager.set_new_frame(frame=frame, frame_idx=frame_idx, channel_name=channel_name)
                self._captured_frames += 1
            except Exception as e:
                self.log.error(f"Error during frame acquisition: {e}")
                break
        self._batch_halt_event.clear()  # Reset the halt event for future acquisitions
        self.log.info(f"Batch acquisition complete. Captured {self._captured_frames} frames.")
        completion_notifier.set()

    def cancel_batch_acquisition(self) -> None:
        """Cancel the current batch acquisition if it is running."""
        if self._batch_capture_thread and self._batch_capture_thread.is_alive():
            self.log.info("Cancelling batch acquisition.")
            self._batch_halt_event.set()
            self._batch_capture_thread.join(timeout=5)

    def finalize(self) -> None:
        self.log.info("Finalizing stack...")

        # Ensure current batch thread is finished if it was running
        if self._batch_capture_thread and self._batch_capture_thread.is_alive():
            self.log.warning("Finalizing stack while batch thread is still active. Waiting...")
            # A halt event might be useful to signal the thread
            # For now, just wait for its natural completion or timeout
            self._batch_completion_event.wait(timeout=2 * 60)  # Or join the thread
            if self._batch_capture_thread.is_alive():
                self.log.error("Batch thread did not finish during finalize timeout!")

        try:
            self._writer.close()
            self.log.info("Stack finalized.")
        except Exception as e:
            self.log.error(f"Error during finalization: {e}")
            raise


class PipelineState(StrEnum):
    IDLE = "idle"
    LIVE_VIEW = "live_view"  # Encompasses the entire live view operation
    STACK_ACQUISITION = "stack_acquisition"  # Pipeline is dedicated to a runner
    ERROR = "error"  # If pipeline itself encounters an unrecoverable issue


class CameraPipeline:
    def __init__(self, camera: "VoxelCamera", io_manager: "IOManager"):
        self.name = f"{camera.name} Pipeline"
        self.log = get_component_logger(self)
        self._camera = camera
        self._io_manager = io_manager

        self._state_lock = threading.Lock()
        self._state = PipelineState.IDLE

        self.preview_manager = PreviewManager()

        self._active_acq_runner: StackAcquisitionRunner | None = None
        self._live_view_thread: threading.Thread | None = None
        self._live_view_halt_event = threading.Event()

    @property
    def state(self) -> PipelineState:
        with self._state_lock:
            return self._state

    def _set_state(self, new_state: PipelineState, action_description: str = ""):
        # Internal helper, assumes caller (public method) has ensured validity
        with self._state_lock:
            if self._state != new_state:
                self.log.info(f"Pipeline state change ({action_description}): {self._state.name} -> {new_state.name}")
                self._state = new_state

    # --- Live View ---
    def start_live_view(self, channel_name: str) -> None:
        with self._state_lock:
            if self._state != PipelineState.IDLE:
                raise RuntimeError(f"Cannot start live view. Pipeline is busy (mode: {self._state.name}).")
            self._set_state(PipelineState.LIVE_VIEW, "start_live_view")

        try:
            self.log.info("Starting live view setup...")
            self._camera.prepare()
            self._camera.start(frame_count=None)
            self._live_view_halt_event.clear()
            self._live_view_thread = threading.Thread(
                target=self._run_live_view_target, args=(channel_name,), daemon=True
            )
            self._live_view_thread.start()
            self.log.info("Live view active.")
        except Exception as e:
            self.log.error(f"Error during live view start: {e}", exc_info=True)
            self._camera.stop()
            self._live_view_thread = None
            self._set_state(PipelineState.IDLE, "live_view_start_failed_rollback")
            raise

    def _run_live_view_target(self, channel_name: str) -> None:
        frame_count = 0
        try:
            self.log.info("Live view loop started.")
            while not self._live_view_halt_event.is_set():
                try:
                    frame = self._camera.grab_frame()
                    self.preview_manager.set_new_frame(frame=frame, frame_idx=frame_count, channel_name=channel_name)
                    frame_count += 1
                except Exception as e_grab:  # Catch errors within the loop
                    self.log.error(f"Error in live view grab/preview: {e_grab}", exc_info=True)
                    if not self._live_view_halt_event.wait(0.1):  # Brief pause on error
                        pass  # Continue if not halted
                    else:
                        break  # Halted during error pause
            self.log.info(f"Live view loop terminated. Frames: {frame_count}")
        except Exception as e_thread:
            self.log.error(f"Error in live view thread: {e_thread}", exc_info=True)
            # If thread crashes, orchestrator won't get a clean stop.
            # The pipeline mode might remain LIVE_VIEW.
            # A robust orchestrator would have timeouts for operations.
        finally:
            self.log.debug("Live view thread finishing...")
            self._camera.stop()
            # if stop_live_view isn't guaranteed to be called by orchestrator after thread ends:
            with self._state_lock:
                if self._state == PipelineState.LIVE_VIEW:  # Only if not already stopped by stop_live_view
                    self._state = PipelineState.IDLE
                    self.log.info("Live view thread ended, pipeline set to IDLE.")
            self._live_view_thread = None

    def stop_live_view(self) -> None:
        if self.state != PipelineState.LIVE_VIEW:
            self.log.warning(f"Stop live view called, but not in live view mode (mode: {self.state}).")
            return

        self.log.info("Stopping live view mode...")
        self._live_view_halt_event.set()
        thread_to_join = self._live_view_thread

        if thread_to_join:
            thread_to_join.join(timeout=30.0)  # Wait for the thread to finish its loop and finally block
            if thread_to_join.is_alive():
                self.log.error("Live view thread did not join cleanly!")
                self._camera.stop()

        # self._live_view_thread should be None now if thread exited cleanly
        self._set_state(PipelineState.IDLE, "stop_live_view")
        self.log.info("Live view stopped.")

    # --- Stack Acquisition ---
    def prepare_stack_acquisition(
        self, config: "StackAcquisitionConfig", writer_name: str, transfer_name: str | None = None
    ) -> None:  # No longer returns runner directly if orchestrator doesn't need it
        with self._state_lock:
            if self._state != PipelineState.IDLE:
                raise RuntimeError(f"Cannot prepare stack. Pipeline is busy (mode: {self._state.name}).")
            self._set_state(PipelineState.STACK_ACQUISITION, "prepare_stack")

        try:
            self.log.info(f"Preparing stack acquisition: {config.channel_name}")
            writer = self._io_manager.get_writer_instance(writer_name)
            transfer = self._io_manager.get_transfer_instance(transfer_name) if transfer_name else None

            self._active_acq_runner = StackAcquisitionRunner(
                camera=self._camera,
                writer=writer,
                config=config,
                preview_manager=self.preview_manager,
                transfer=transfer,
            )
            # StackAcquisitionRunner __init__ does camera.prepare, writer.configure/start
            self.log.info(f"Stack acquisition prepared for {config.channel_name}.")
        except Exception as e:
            self.log.error(f"Failed to prepare stack acquisition: {e}", exc_info=True)
            self._active_acq_runner = None  # Ensure runner is cleared
            self._set_state(PipelineState.IDLE, "stack_prepare_failed_rollback")
            raise

    def acquire_batch(self, start_idx: int, end_idx: int, start_trigger: threading.Event) -> threading.Event:
        # Assumes orchestrator has called prepare_stack_acquisition successfully.
        if self.state != PipelineState.STACK_ACQUISITION or not self._active_acq_runner:
            raise RuntimeError("Pipeline not prepared for stack acquisition or no runner.")

        # self.log.debug(f"Pipeline delegating acquire_batch to runner for {self._active_acq_runner._writer.config.channel_name}")
        return self._active_acq_runner.acquire_batch(start_idx, end_idx, start_trigger)

    def cancel_batch_acquisition(self) -> None:
        if self.state == PipelineState.STACK_ACQUISITION and self._active_acq_runner:
            self.log.info("Pipeline canceling active acquisition runner's batch.")
            self._active_acq_runner.cancel_batch_acquisition()
        else:
            self.log.warning(f"No active stack acquisition to cancel. State: {self.state.name}")

    def finalize_stack_acquisition(self, abort: bool = False) -> None:
        if not self._active_acq_runner:
            self.log.info("No active acquisition runner to finalize.")
            self._set_state(PipelineState.IDLE, "finalize_no_runner")
            return
        if self.state != PipelineState.STACK_ACQUISITION and self._active_acq_runner is not None:
            self.log.warning(
                "Finalize called, but pipeline not in STACK_ACQUISITION state. Active runner will be finalized anyway."
            )
            self._set_state(PipelineState.STACK_ACQUISITION, "correcting inconsistency to allow finalizing runner")
            return self.finalize_stack_acquisition(abort=abort)

        runner = self._active_acq_runner
        self.log.info(f"Finalizing stack acquisition for runner {runner._writer.config.channel_name}. Aborted: {abort}")
        try:
            if abort:
                runner.cancel_batch_acquisition()
            runner.finalize()
        except Exception as e:
            self.log.error(f"Error during runner finalization via pipeline: {e}", exc_info=True)
            # Pipeline should probably go to an ERROR state or at least log this severely
        finally:
            self._active_acq_runner = None
            self._set_state(PipelineState.IDLE, "stack_acquisition_finalized")
            self.log.info("Pipeline mode set to IDLE.")

    def force_stop_all_activity(self) -> None:
        """A more forceful stop for any activity."""
        self.log.warning("Force stop all activity requested for pipeline.")
        current_mode = self.state  # Read once

        if current_mode == PipelineState.LIVE_VIEW:
            self.log.info("Force stopping live view...")
            self._live_view_halt_event.set()
            thread = self._live_view_thread
            if thread and thread.is_alive():
                thread.join(timeout=1.0)  # Brief join
                if thread.is_alive():
                    self.log.error("Live view thread still alive after force stop join.")
            self._live_view_thread = None  # Clear
            self._camera.stop()

        elif current_mode == PipelineState.STACK_ACQUISITION and self._active_acq_runner:
            self.log.info("Force stopping stack acquisition runner...")
            self._active_acq_runner.cancel_batch_acquisition()
            self._active_acq_runner = None

        else:  # IDLE or ERROR
            self.log.info(f"No active operation to force stop. Current mode: {current_mode.name}")

        self._set_state(PipelineState.IDLE, "force_stop_all_activity")
        self.log.info("Pipeline forced to IDLE state.")
