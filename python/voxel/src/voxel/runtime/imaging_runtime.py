from enum import StrEnum
import threading
from typing import TYPE_CHECKING

from voxel.utils.log import VoxelLogging

from .live_viewer import LiveViewer
from .preview import PreviewConfigUpdates, PreviewFramePublisher, PreviewGenerator
from .stack_acquisition import BatchStatus, StackAcquisitionConfig, StackAcquisitionRunner

if TYPE_CHECKING:
    from voxel.devices import VoxelCamera

    from .io import IOManager


class ImagingRuntimeMode(StrEnum):
    IDLE = "idle"
    PREVIEW = "preview"
    ACQUISITION = "acquisition"
    ERROR = "error"


class ImagingRuntime:
    def __init__(self, camera: "VoxelCamera", io_manager: "IOManager", preview_pub: PreviewFramePublisher):
        self.name = f"{camera.uid} Pipeline"
        self.log = VoxelLogging.get_logger(object=self)
        self._camera = camera
        self._io_manager = io_manager

        self._previewer = PreviewGenerator(preview_pub)

        self._state_lock = threading.Lock()

        self._active_acq_runner: StackAcquisitionRunner | None = None
        self._active_live_viewer: LiveViewer | None = None  # noqa: F821

    @property
    def camera(self) -> "VoxelCamera":
        """Expose the camera for external access."""
        return self._camera

    @property
    def available_writers(self) -> set[str]:
        return self._io_manager.available_writers

    @property
    def available_transfers(self) -> set[str]:
        return self._io_manager.available_transfers

    def get_current_mode(self) -> ImagingRuntimeMode:
        """Get the current mode of the pipeline."""
        with self._state_lock:
            if self._active_acq_runner and self._active_live_viewer:
                self.log.warning("Both acquisition runner and live viewer are active. This is unexpected.")
                return ImagingRuntimeMode.ERROR
            if self._active_acq_runner:
                return ImagingRuntimeMode.ACQUISITION
            elif self._active_live_viewer:
                return ImagingRuntimeMode.PREVIEW
            else:
                return ImagingRuntimeMode.IDLE

    def get_acquisition_status(self) -> dict[tuple[int, int], BatchStatus] | None:
        if self._active_acq_runner:
            return self._active_acq_runner.get_acquisition_status()

    def update_preview_config(self, options: "PreviewConfigUpdates") -> None:
        """Update the preview configuration."""
        self._previewer.update_config(options)

    # --- Live View ---
    def _on_live_view_stop(self, frame_count: int):
        self.log.info(f"Viewer has stopped live vidgets. Frames captured: {frame_count}")

    def start_live_view(self, channel_name: str) -> None:
        self._active_live_viewer = LiveViewer(
            camera=self._camera,
            previewer=self._previewer,
            on_stop=self._on_live_view_stop,
        )
        self._active_live_viewer.start(channel_name)

    def stop_live_view(self) -> None:
        if not self._active_live_viewer:
            self.log.warning("Stop live view called, but no active viewer.")
            return
        self._active_live_viewer.stop()
        self._active_live_viewer = None

    # --- Stack Acquisition ---
    def prepare_stack_acquisition(
        self, config: "StackAcquisitionConfig", writer_name: str, transfer_name: str | None = None
    ) -> None:
        if self._active_live_viewer is not None:
            self.log.warning("Preparing stack acquisition while live view is active. Stopping live view first.")
            self.stop_live_view()

        if self._active_acq_runner is not None:
            self.log.warning(f"Unable to prepare stack {config.channel_name}. Another runner is already active.")
            return

        try:
            self.log.info(f"Preparing stack acquisition: {config.channel_name}")
            writer = self._io_manager.get_writer_instance(writer_name)
            transfer = self._io_manager.get_transfer_instance(transfer_name) if transfer_name else None

            self._active_acq_runner = StackAcquisitionRunner(
                camera=self._camera,
                writer=writer,
                config=config,
                preview_generator=self._previewer,
                transfer=transfer,
            )
            self.log.info(f"Stack acquisition prepared for {config.channel_name}.")
        except Exception as e:
            self.log.error(f"Failed to prepare stack acquisition: {e}", exc_info=True)
            self._active_acq_runner = None
            raise

    def acquire_batch(self, start_idx: int, end_idx: int, start_trigger: threading.Event) -> threading.Event:
        """
        Acquire a batch of frames from start_idx to end_idx.
        Returns a completion event that will signal when the batch acquisition is complete.
        - users will need to check the pipeline state upon completion to determine if it was successful or not.
        """
        if not self._active_acq_runner:
            raise RuntimeError("Pipeline not prepared for stack acquisition or no runner.")

        return self._active_acq_runner.acquire_batch(start_idx, end_idx, start_trigger)

    def cancel_batch_acquisition(self) -> None:
        if self._active_acq_runner:  # and self._active_acq_runner.is_acquiring_batch():
            self._active_acq_runner.abort_batch_acquisition()
        else:
            self.log.warning("No active stack acquisition to cancel.")

    def finalize_stack_acquisition(self, abort: bool = False) -> None:
        if not self._active_acq_runner:
            self.log.info("No active acquisition runner to finalize.")
            return

        runner = self._active_acq_runner
        self.log.info(f"Finalizing stack acquisition for runner {runner._writer.config.channel_name}. Aborted: {abort}")
        try:
            if abort:
                runner.abort_batch_acquisition()
            runner.finalize()
        except Exception as e:
            self.log.error(f"Error during runner finalization via pipeline: {e}", exc_info=True)
        finally:
            self._active_acq_runner = None
