import threading
import time
from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
import uuid

import numpy as np

from voxel.frame_stack import StackAcquisitionConfig
from voxel.io.transfers.base import VoxelFileTransfer
from voxel.io.writers.base import VoxelWriter, WriterConfig
from voxel.utils.common import get_available_disk_space_mb
from voxel.utils.log_config import get_component_logger, get_logger
from voxel.utils.vec import Vec3D

from .preview import NewFrameCallback, PreviewFrame, PreviewManager

if TYPE_CHECKING:
    from voxel.devices.camera import VoxelCamera, VoxelCameraProxy
    from voxel.io.manager import IOManager


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


class ICameraPipeline(ABC):
    @property
    @abstractmethod
    def camera(self) -> "VoxelCamera | VoxelCameraProxy": ...

    @property
    @abstractmethod
    def available_writers(self) -> list[str]: ...

    @property
    @abstractmethod
    def available_transfers(self) -> list[str]: ...

    @property
    @abstractmethod
    def state(self) -> PipelineState: ...

    # --- Live View ---
    @abstractmethod
    def start_live_view(self, channel_name: str) -> None: ...

    @abstractmethod
    def stop_live_view(self) -> None: ...

    # --- Stack Acquisition ---
    @abstractmethod
    def prepare_stack_acquisition(
        self,
        config: "StackAcquisitionConfig",
        writer_name: str,
        transfer_name: str | None = None,
    ) -> None: ...

    @abstractmethod
    def acquire_batch(self, start_idx: int, end_idx: int, start_trigger: threading.Event) -> threading.Event: ...

    @abstractmethod
    def cancel_batch_acquisition(self) -> None: ...

    @abstractmethod
    def finalize_stack_acquisition(self, abort: bool = False) -> None: ...

    @abstractmethod
    def force_stop_all_activity(self) -> None: ...


class CameraPipeline(ICameraPipeline):
    def __init__(self, camera: "VoxelCamera", io_manager: "IOManager"):
        self.name = f"{camera.name} Pipeline"
        self.log = get_component_logger(self)
        self._camera = camera
        self._io_manager = io_manager

        self._state_lock = threading.Lock()
        self._state = PipelineState.IDLE

        self._new_frame_observers: dict[str, NewFrameCallback] = {}
        self._preview_manager = PreviewManager(on_new_frame=self._notify_new_frame_observers, preview_width=1024)

        self._active_acq_runner: StackAcquisitionRunner | None = None
        self._live_view_thread: threading.Thread | None = None
        self._live_view_halt_event = threading.Event()

    @property
    def camera(self) -> "VoxelCamera":
        """Expose the camera for external access."""
        return self._camera

    @property
    def available_writers(self) -> list[str]:
        return self._io_manager.available_writers

    @property
    def available_transfers(self) -> list[str]:
        return self._io_manager.available_transfers

    @property
    def state(self) -> PipelineState:
        with self._state_lock:
            return self._state

    def register_new_frame_observer(self, observer: NewFrameCallback) -> str:
        """Register a callback to be notified of new preview frames."""
        observer_id = str(uuid.uuid4())
        self._new_frame_observers[observer_id] = observer
        self.log.debug(f"New frame observer registered: {observer_id}")
        return observer_id

    def unregister_new_frame_observer(self, observer_id: str) -> None:
        """Unregister a callback for new preview frames."""
        if observer_id in self._new_frame_observers:
            del self._new_frame_observers[observer_id]
            self.log.debug(f"New frame observer unregistered: {observer_id}")
        else:
            self.log.warning(f"Attempted to unregister non-existent observer: {observer_id}")

    def _notify_new_frame_observers(self, new_frame: "PreviewFrame") -> None:
        for observer in self._new_frame_observers.values():
            observer(new_frame)

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
                    self._preview_manager.set_new_frame(frame=frame, frame_idx=frame_count, channel_name=channel_name)
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
        self,
        config: "StackAcquisitionConfig",
        writer_name: str,
        transfer_name: str | None = None,
    ) -> None:
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
                preview_manager=self._preview_manager,
                transfer=transfer,
            )
            self.log.info(f"Stack acquisition prepared for {config.channel_name}.")
        except Exception as e:
            self.log.error(f"Failed to prepare stack acquisition: {e}", exc_info=True)
            self._active_acq_runner = None
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


class CameraPipelineService:
    """
    ZeroRPC server that wraps a LocalCameraPipeline"""


class CameraPipelineProxy(ICameraPipeline):
    """
    Proxy for interacting with a remote camera pipeline.
    The preview_frames use a PUSH/PULL model where the server sends frames to the client.
    ...
    """

    pass
