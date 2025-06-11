import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from voxel.devices.base import VoxelDeviceModel
from voxel.devices.interfaces.camera import VoxelCamera, VoxelCameraProxy
from voxel.pipeline.local import (
    IFrameCaptureNode,
    PipelineStatus,
    StackAcquisitionConfig,
)
from voxel.pipeline.preview import NewFrameCallback, PreviewFrame
from voxel.utils.log_config import get_component_logger

if TYPE_CHECKING:
    from voxel.daq.tasks.wavegen import WaveGenTask
    from voxel.devices import VoxelFilter, VoxelLaser


@dataclass
class VoxelChannel:
    """
    The channel coordinates the acq_task (responsible for sending control signals via NI-DAQ)
    while delegating image acquisition and writing to the engine.
    it also handles the laser and filter devices.
    """

    name: str
    engine: IFrameCaptureNode  # Handles camera, writer, preview, and batch acquisition.
    acq_task: "WaveGenTask"  # NI-DAQ task wrapper (with main and trigger tasks).
    laser: "VoxelLaser"
    filter: "VoxelFilter"

    def __post_init__(self):
        self.log = get_component_logger(self)
        # self._current_frame: PreviewFrame | None = None
        self._preview_callbacks: set[NewFrameCallback] = set()

    @property
    def camera(self) -> VoxelCamera | VoxelCameraProxy:
        """Get the camera associated with this channel."""
        return self.engine.camera

    @property
    def is_previewing(self) -> bool:
        """Check if the channel is currently in preview mode."""
        return self.engine.state == PipelineStatus.PREVIEW

    @property
    def is_acquiring(self) -> bool:
        """Check if the channel is currently in acquisition mode."""
        return self.engine.state == PipelineStatus.CONFIGURED or self.engine.state == PipelineStatus.RUNNING

    @property
    def is_active(self) -> bool:
        """Check if the channel is currently active (either previewing or acquiring)."""
        return self.is_previewing or self.is_acquiring

    def register_preview_callback(self, callback: NewFrameCallback) -> None:
        """
        Register a callback to be called when a new preview frame is available.
        The callback should accept a single argument, which will be the new frame.
        """
        self._preview_callbacks.add(callback)

    def unregister_preview_callback(self, callback: NewFrameCallback) -> None:
        """
        Unregister a previously registered preview callback.
        """
        self._preview_callbacks.discard(callback)

    def notify_preview_callbacks(self, frame: PreviewFrame) -> None:
        """
        Notify all registered preview callbacks with the new frame.
        This is called when a new frame is available.
        """
        if not self._preview_callbacks:
            return
        frame = PreviewFrame.unpack(packed_frame=frame) if isinstance(frame, bytes) else frame
        for callback in self._preview_callbacks:
            try:
                # print(f"Notifying callback {callback} with frame {frame.config.frame_idx}")
                callback(frame)
            except Exception as e:
                self.log.error(f"Error in preview callback: {e}")

    def start_preview(self) -> None:
        """Start preview mode by enabling devices and delegating preview to the engine."""
        self.log.info("Starting preview mode.")
        self.laser.enable()
        self.filter.enable()
        self.acq_task.regenerate_waveforms()
        self.acq_task.trigger_task.configure(num_samples=None)
        self.acq_task.start()
        self.engine.start_preview(on_new_frame=self.notify_preview_callbacks)

    def stop_preview(self) -> None:
        """Stop preview mode by stopping the engine and disabling devices."""
        self.log.info("Stopping preview mode.")
        self.engine.stop_preview()
        self.laser.disable()
        self.filter.disable()
        self.acq_task.stop()

    def get_latest_preview(self) -> PreviewFrame | None:
        """Get the latest frame from the engine."""
        return self.engine.get_latest_preview()

    def acquire_stack(self, config: "StackAcquisitionConfig") -> None:
        """
        Perform stack acquisition:
          1. Configure the NI-DAQ task (acq_task) with appropriate waveforms
             and adjust the trigger frequency based on the camera's frame rate.
          2. Prepare the engine for acquisition (which configures the writer and waits for disk space)
             and obtain the frame ranges.
          3. Start the main acq_task.
          4. For each batch: configure and start the trigger task for the number of frames,
             delegate frame acquisition to the engine, and then stop the trigger.
          5. Stop the acq_task and finalize acquisition via the engine.
        """

        self.log.info("Starting stack acquisition.")

        # If preview is active, stop it first.
        if self.engine.state == PipelineStatus.PREVIEW:
            self.stop_preview()

        def acquisition_thread():
            # Configure NI-DAQ task for acquisition.
            self.acq_task.regenerate_waveforms()
            self.acq_task.write()
            # Adjust trigger frequency based on camera frame rate.
            self.acq_task.trigger_task.freq_hz = self.engine.frame_rate_hz * 0.75

            # Prepare the engine for acquisition and get frame ranges.
            frame_ranges = self.engine.prepare_stack_acquisition(config)

            self.acq_task.start()
            for frame_range in frame_ranges:
                self.acq_task.trigger_task.configure(num_samples=len(frame_range))
                self.acq_task.trigger_task.start()
                # Acquire the current batch with the engine.
                self.engine.acquire_batch(frame_range, on_new_frame=self.notify_preview_callbacks)
                self.acq_task.trigger_task.stop()
            self.acq_task.stop()
            self.engine.finalize_stack_acquisition()
            self.log.info("Stack acquisition complete.")

        threading.Thread(target=acquisition_thread, daemon=True).start()

    @property
    def snapshot(self) -> list[VoxelDeviceModel]:
        """
        Return a snapshot of the channel's devices.
        This is used for API responses.
        """
        return [self.camera.snapshot, self.laser.snapshot, self.filter.snapshot]
