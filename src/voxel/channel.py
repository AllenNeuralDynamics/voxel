from dataclasses import dataclass
from typing import Self, cast

from voxel.devices import VoxelDevice, VoxelLaser
from voxel.devices.camera import VoxelCamera
from voxel.devices.filter_wheel import VoxelFilterWheel
from voxel.instrument import ChannelConfiguration, Instrument, OpticalPathUnit
from voxel.pipeline.local import (
    ICameraPipeline,
    PipelineStatus,
    StackAcquisitionConfig,
)
from voxel.pipeline.preview_frame import NewFrameCallback, PreviewFrame
from voxel.settings import ConfiguredDevice, SettingsBlock
from voxel.utils.log_config import get_component_logger


@dataclass
class DetectionUnit:
    camera: ConfiguredDevice[VoxelCamera]
    filter_wheels: dict[str, VoxelFilterWheel]
    aux_devices: dict[str, ConfiguredDevice[VoxelDevice]]
    pipeline: ICameraPipeline

    def __post_init__(self):
        self.log = get_component_logger(self)

    @property
    def name(self) -> str:
        """Get the name of the detection unit."""
        return f"{self.camera.name}_du"

    @property
    def devices(self) -> dict[str, ConfiguredDevice[VoxelDevice]]:
        """Get the devices associated with the detection unit."""
        return {self.camera.name: cast(ConfiguredDevice[VoxelDevice], self.camera), **self.aux_devices}

    @property
    def settings(self) -> dict[str, SettingsBlock]:
        return {device.name: device.settings for device in self.devices.values()}

    def set_filters(self, filter_selections: dict[str, str]) -> None:
        """
        Set the filters for the filter wheels in the detection unit.
        :param filter_selections: A dictionary mapping filter wheel names to filter names.
        """
        for wheel_name, filter_name in filter_selections.items():
            if wheel_name in self.filter_wheels:
                self.filter_wheels[wheel_name].current_filter = filter_name
            else:
                self.camera.log.error(f"Filter wheel '{wheel_name}' not found in the detection unit.")


@dataclass
class IlluminationUnit:
    laser: ConfiguredDevice[VoxelLaser]
    aux_devices: dict[str, ConfiguredDevice[VoxelDevice]]

    @property
    def name(self) -> str:
        """Get the name of the illumination unit."""
        return f"{self.laser.name}_iu"

    @property
    def devices(self) -> dict[str, ConfiguredDevice[VoxelDevice]]:
        """Get the devices associated with the illumination unit."""
        return {self.laser.name: cast(ConfiguredDevice[VoxelDevice], self.laser), **self.aux_devices}

    @property
    def settings(self) -> dict[str, SettingsBlock]:
        return {device.name: device.settings for device in self.devices.values()}

    def enable(self) -> None:
        """Enable the laser and any other auxiliary devices."""
        self.laser.device.enable()

    def disable(self) -> None:
        """Disable the laser and any other auxiliary devices."""
        self.laser.device.disable()


@dataclass
class ImagingChannel:
    name: str
    detection: DetectionUnit
    illumination: IlluminationUnit
    filters: dict[str, str]

    def __post_init__(self):
        self.log = get_component_logger(self)
        self._validate_filter_assignments()
        self._preview_callbacks: set[NewFrameCallback] = set()

    def start_preview(self) -> None:
        """Start preview mode by enabling devices and delegating preview to the engine."""
        self.log.info("Starting preview mode.")
        # TODO: Remember to have the ImagingGroup setup the acquisition task
        self.detection.set_filters(self.filters)
        self.detection.pipeline.start_preview(on_new_frame=self.notify_preview_callbacks)
        self.illumination.enable()

    def stop_preview(self) -> None:
        """Stop preview mode by stopping the engine and disabling devices."""
        self.log.info("Stopping preview mode.")
        self.detection.pipeline.stop_preview()
        self.illumination.disable()
        # TODO: Remember to have the ImagingGroup stop the acquisition task

    def prepare_stack_acquisition(self, config: StackAcquisitionConfig) -> list[range]:
        """
        Prepare the detection unit for stack acquisition.
        :param config: The stack acquisition configuration.
        :return: A list of frame ranges for the acquisition. Used when calling acquire_batch.
        """
        if self.detection.pipeline.state == PipelineStatus.PREVIEW:
            self.stop_preview()
        self.detection.set_filters(self.filters)
        return self.detection.pipeline.prepare_stack_acquisition(config)

    def acquire_batch(self, frame_range: range, on_new_frame: NewFrameCallback) -> None:
        """
        Acquire a batch of frames from the detection unit.
        :param frame_range: The range of frames to acquire.
        :param on_new_frame: Callback function to be called when a new frame is available.
        """
        self.detection.pipeline.acquire_batch(frame_range, on_new_frame=on_new_frame)

    def finalize_stack_acquisition(self) -> None:
        """Finalize the stack acquisition process."""
        self.detection.pipeline.finalize_stack_acquisition()
        self.log.info("Stack acquisition complete.")

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

    def _validate_filter_assignments(self) -> None:
        """
        Validate the filter assignments against the available filter wheels.
        Raise an error if any filter assignment is invalid.
        """
        errors = []
        for wheel_name, filter_name in self.filters.items():
            if wheel_name not in self.detection.filter_wheels:
                errors.append(f"Filter wheel '{wheel_name}' not found in the detection unit.")
            elif filter_name not in self.detection.filter_wheels[wheel_name].filters.values():
                errors.append(f"Filter '{filter_name}' not found in filter wheel '{wheel_name}'.")

        if errors:
            raise ValueError("\n".join(errors))

    @classmethod
    def from_config(cls, channel_name: str, config: ChannelConfiguration, instrument: Instrument) -> Self:
        """
        Create a Channel instance from a configuration and an instrument.
        :param config: The channel configuration containing the settings.
        :param instrument: The instrument to which the channel belongs.
        :return: A Channel instance.
        """

        def create_configured_aux_devices(assembly: OpticalPathUnit) -> dict[str, ConfiguredDevice[VoxelDevice]]:
            devices = {}
            for name in assembly.aux_devices:
                device = instrument.devices[name]
                settings = config.settings.get(name)
                devices[name] = ConfiguredDevice(device=device, settings=settings)
            return devices

        detection_setup = instrument.assembly.detection[config.detection]
        camera = instrument.cameras[config.detection]
        filter_wheels = {name: instrument.filter_wheels[name] for name in detection_setup.filter_wheels}

        detection_unit = DetectionUnit(
            camera=ConfiguredDevice(camera, config.settings[config.detection]),
            filter_wheels=filter_wheels,
            aux_devices=create_configured_aux_devices(detection_setup),
            pipeline=instrument.pipelines[config.detection],
        )

        illumination_setup = instrument.assembly.illumination[config.illumination]
        laser = instrument.lasers[config.illumination]

        illumination_unit = IlluminationUnit(
            laser=ConfiguredDevice(laser, config.settings[config.illumination]),
            aux_devices=create_configured_aux_devices(illumination_setup),
        )

        return cls(
            name=channel_name,
            detection=detection_unit,
            illumination=illumination_unit,
            filters=config.filters,
        )

    def to_config(self) -> tuple[str, ChannelConfiguration]:
        """
        Convert the channel instance to a ChannelConfiguration object.
        :return: A tuple containing the channel name and a ChannelConfiguration object representing the channel.
        """
        return (
            self.name,
            ChannelConfiguration(
                detection=self.detection.camera.name,
                illumination=self.illumination.laser.name,
                filters=self.filters,
                settings={**self.detection.settings, **self.illumination.settings},
            ),
        )

    # TODO: Use the ImagingGroup to incorporate pipeline steps with the NI-DAQ task steps.
    # def acquire_stack(self, config: "StackAcquisitionConfig") -> None:
    #     """
    #     Perform stack acquisition:
    #       1. Configure the NI-DAQ task (acq_task) with appropriate waveforms
    #          and adjust the trigger frequency based on the camera's frame rate.
    #       2. Prepare the engine for acquisition (which configures the writer and waits for disk space)
    #          and obtain the frame ranges.
    #       3. Start the main acq_task.
    #       4. For each batch: configure and start the trigger task for the number of frames,
    #          delegate frame acquisition to the engine, and then stop the trigger.
    #       5. Stop the acq_task and finalize acquisition via the engine.
    #     """

    #     self.log.info("Starting stack acquisition.")

    #     # If preview is active, stop it first.
    #     if self.detection.pipeline.state == PipelineStatus.PREVIEW:
    #         self.stop_preview()

    #     def acquisition_thread():
    #         # Configure NI-DAQ task for acquisition.
    #         self.acq_task.regenerate_waveforms()
    #         self.acq_task.write()
    #         # Adjust trigger frequency based on camera frame rate.
    #         self.acq_task.trigger_task.freq_hz = self.detection.pipeline.frame_rate_hz * 0.75

    #         # Prepare the engine for acquisition and get frame ranges.
    #         frame_ranges = self.detection.pipeline.prepare_stack_acquisition(config)

    #         self.acq_task.start()
    #         for frame_range in frame_ranges:
    #             self.acq_task.trigger_task.configure(num_samples=len(frame_range))
    #             self.acq_task.trigger_task.start()
    #             # Acquire the current batch with the engine.
    #             self.detection.pipeline.acquire_batch(frame_range, on_new_frame=self.notify_preview_callbacks)
    #             self.acq_task.trigger_task.stop()
    #         self.acq_task.stop()
    #         self.detection.pipeline.finalize_stack_acquisition()
    #         self.log.info("Stack acquisition complete.")

    #     threading.Thread(target=acquisition_thread, daemon=True).start()
