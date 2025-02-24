import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING


from voxel.devices.camera import VoxelCamera, VoxelCameraProxy
from voxel.engine.local import AcquisitionEngineBase, EngineStatus, StackAcquisitionConfig
from voxel.engine.preview import PreviewFrame
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
    engine: AcquisitionEngineBase  # Handles camera, writer, preview, and batch acquisition.
    acq_task: "WaveGenTask"  # NI-DAQ task wrapper (with main and trigger tasks).
    laser: "VoxelLaser"
    filter: "VoxelFilter"

    def __post_init__(self):
        self.log = get_component_logger(self)
        self._current_frame: PreviewFrame | None = None

    @property
    def camera(self) -> VoxelCamera | VoxelCameraProxy:
        """Get the camera associated with this channel."""
        return self.engine.camera

    def _set_current_frame(self, frame: PreviewFrame) -> None:
        """Set the current frame for the channel."""
        self._current_frame = frame

    def start_preview(self) -> None:
        """Start preview mode by enabling devices and delegating preview to the engine."""
        self.log.info("Starting preview mode.")
        self.laser.enable()
        self.filter.enable()
        self.acq_task.regenerate_waveforms()
        self.acq_task.trigger_task.configure(num_samples=None)
        self.acq_task.start()
        self.engine.start_preview(on_new_frame=self._set_current_frame)

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
        if self.engine.state == EngineStatus.PREVIEW:
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
                self.engine.acquire_batch(frame_range, on_new_frame=self._set_current_frame)
                self.acq_task.trigger_task.stop()
            self.acq_task.stop()
            self.engine.finalize_stack_acquisition()
            self.log.info("Stack acquisition complete.")

        threading.Thread(target=acquisition_thread, daemon=True).start()
