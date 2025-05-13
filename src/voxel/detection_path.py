from dataclasses import dataclass, field
import threading
from voxel.daq.tasks.wavegen import WaveGenTask
from voxel.devices.base import VoxelDevice, VoxelDeviceType
from voxel.devices.camera import VoxelCamera, VoxelCameraProxy
from voxel.devices.laser import VoxelLaser
from voxel.devices.linear_axis import VoxelLinearAxis
from voxel.engine.local import AcquisitionEngineBase, EngineStatus, StackAcquisitionConfig
from voxel.engine.preview import NewFrameCallback, PreviewFrame
from voxel.utils.descriptors.enumerated import enumerated_string
from voxel.utils.log_config import get_component_logger


class FilterWheel(VoxelDevice):
    def __init__(self, name: str, filters: list[str]) -> None:
        super().__init__(name=name, device_type=VoxelDeviceType.FILTER_WHEEL)
        self._filters = filters
        self._current_filter = self._filters[0] if filters else "None"

    @property
    def filters(self) -> dict[int, str]:
        """Return a dictionary of filter names and their corresponding positions."""
        return dict(enumerate(self._filters))

    @enumerated_string(options=lambda self: self._filters)
    def current_filter(self) -> str:
        return self._current_filter

    @current_filter.setter
    def current_filter(self, filter_name: str) -> None:
        if filter_name in self._filters:
            self._current_filter = filter_name
        else:
            raise ValueError(f"Filter '{filter_name}' not found in the filter wheel.")


@dataclass
class IlluminationChannel:
    """
    An illumination channel represents a single channel of illumination in a voxel instrument. It is responsible for
    managing the laser and filter devices associated with that channel. The channel also holds the filter setting
    for the associated filterwheel.
    """

    laser: VoxelLaser
    filter: str
    name: str = ""
    axes: list[VoxelLinearAxis] = field(default_factory=list)

    def __post_init__(self):
        if self.name == "":
            self.name = f"{self.laser.name}_{self.filter}"


@dataclass
class DetectionPath:
    """
    Represents a detection path in a voxel instrument. This primarily includes a camera encapsulated in an
    AcquisitionEngine, a filterwheel, and optionally a focusing axis. A detection path must have one or more
    illumination channels associated with it each with its own laser and filter and an associated filter setting on the
    filterwheel. The detection path is also responsible for managing a WaveGenTask (NI-DAQ task wrapper) for triggering
    the camera, laser, ETL and other devices.
    """

    def __init__(
        self,
        name: str,
        engine: AcquisitionEngineBase,
        filter_wheel: FilterWheel,
        channels: dict[str, IlluminationChannel],
        acq_task: WaveGenTask,
        focusing_axis: VoxelLinearAxis | None,
    ) -> None:
        self.name = name
        self.log = get_component_logger(self)

        self._validate_channels(channels, filter_wheel)
        self._filter_wheel = filter_wheel
        self._channels = channels
        self._active_channel: IlluminationChannel = next(iter(self._channels.values()))

        self._engine = engine
        self._acq_task = acq_task
        self._focusing_axis = focusing_axis

        self._preview_callbacks: set[NewFrameCallback] = set()

    @property
    def channels(self) -> dict[str, IlluminationChannel]:
        """Get the channels associated with this detection path."""
        return self._channels

    def switch_channel(self, channel_name: str) -> IlluminationChannel | None:
        """
        Switch to a different illumination channel by name.
        Returns the active channel if successful, or None if the channel is not found.
        Disables all lasers and sets the filter wheel to the new channel's filter.
        """
        for channel_obj in self._channels.values():
            channel_obj.laser.disable()

        target_channel = self._channels.get(channel_name)
        if target_channel:
            self._filter_wheel.current_filter = target_channel.filter
            self._active_channel = target_channel
            self.log.info(f"Switched to channel: {channel_name}")
            return self._active_channel
        else:
            self.log.error(f"Channel '{channel_name}' not found in this detection path.")
            return None

    @property
    def active_channel(self) -> IlluminationChannel:
        """Get the current illumination channel."""
        return self._active_channel

    @property
    def camera(self) -> VoxelCamera | VoxelCameraProxy:
        """Get the camera associated with this channel."""
        return self._engine.camera

    @property
    def filter_wheel(self) -> FilterWheel:
        """Get the filter wheel associated with this detection path."""
        return self._filter_wheel

    @property
    def focusing_axis(self) -> VoxelLinearAxis | None:
        """Get the focusing axis associated with this detection path."""
        return self._focusing_axis

    @property
    def state(self) -> EngineStatus:
        """Get the status of the detection path."""
        return self._engine.state

    def get_latest_preview_frame(self) -> PreviewFrame | None:
        """Get the latest preview frame from the engine."""
        return self._engine.get_latest_preview()

    def start_preview(self, channel_name: str) -> None:
        """Start preview mode by enabling devices and delegating preview to the engine."""
        self.log.info(f"Starting preview for detection path: {self.name} on channel: {channel_name}")
        if channel := self.switch_channel(channel_name):
            channel.laser.enable()
            self._acq_task.regenerate_waveforms()
            self._acq_task.trigger_task.configure(num_samples=None)
            self._acq_task.start()
            self._engine.start_preview(on_new_frame=self.notify_preview_callbacks)
        else:
            self.log.error(f"Channel '{channel_name}' not found in this detection path. Cannot start preview.")

    def stop_preview(self) -> None:
        """Stop preview mode by stopping the engine and disabling devices."""
        self.log.info("Stopping preview mode.")
        self._engine.stop_preview()
        self._active_channel.laser.disable()
        self._acq_task.stop()

    def acquire_stack(self, config: StackAcquisitionConfig) -> None:
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
        self.log.info(f"starting stack acquisition on channel: {config.channel_name}.")

        if self._engine.state == EngineStatus.PREVIEW:
            self.stop_preview()

        def acquisition_thread():
            # Configure NI-DAQ task for acquisition.
            self._acq_task.regenerate_waveforms()
            self._acq_task.write()
            # Adjust trigger frequency based on camera frame rate.
            self._acq_task.trigger_task.freq_hz = self._engine.frame_rate_hz * 0.75

            # Prepare the engine for acquisition and get frame ranges.
            frame_ranges = self._engine.prepare_stack_acquisition(config)

            self._acq_task.start()
            for frame_range in frame_ranges:
                self._acq_task.trigger_task.configure(num_samples=len(frame_range))
                self._acq_task.trigger_task.start()
                # Acquire the current batch with the engine.
                self._engine.acquire_batch(frame_range, on_new_frame=self.notify_preview_callbacks)
                self._acq_task.trigger_task.stop()
            self._acq_task.stop()
            self._engine.finalize_stack_acquisition()
            self.log.info("Stack acquisition complete.")

        if channel := self.switch_channel(config.channel_name):
            channel.laser.enable()
            threading.Thread(target=acquisition_thread, daemon=True).start()
        else:
            self.log.error(f"Channel '{config.channel_name}' not found in detection path. Cannot start acquisition.")

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

    @staticmethod
    def _validate_channels(channels: dict[str, IlluminationChannel], filterwheel: FilterWheel) -> None:
        """
        Validate the channels to ensure that each channel has a unique laser and that the filter setting is valid.
        Raises ValueError if any channel has a duplicate laser or an invalid filter setting.
        """
        errors = []
        seen_lasers = set()
        valid_filters = set(filterwheel.filters.values())

        for name, channel in channels.items():
            # Check for duplicate lasers
            if channel.laser in seen_lasers:
                errors.append(f"Duplicate laser '{channel.laser.name}' found in channel '{name}'.")
            else:
                seen_lasers.add(channel.laser)

            # Check for invalid filter setting
            if channel.filter not in valid_filters:
                errors.append(
                    f"Invalid filter setting '{channel.filter}' in channel '{name}'. Valid filters are: {', '.join(valid_filters)}."
                )

        if errors:
            raise ValueError("Channel validation failed:\n" + "\n".join(errors))
