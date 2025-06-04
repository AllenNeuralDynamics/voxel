from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
import threading
import time
from typing import Any, Literal, Self, TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from voxel.devices.filter_wheel import VoxelFilterWheel
from voxel.devices.base import VoxelDevice
from voxel.devices.camera import VoxelCamera, VoxelCameraProxy
from voxel.devices.laser import VoxelLaser
from voxel.devices.linear_axis import VoxelLinearAxis
from voxel.devices.rotation_axis import VoxelRotationAxis
from voxel.pipeline.interface import ICameraPipeline, PipelineStatus, StackAcquisitionConfig
from voxel.io.manager import IOManager
from voxel.pipeline.local import LocalCameraPipeline
from voxel.pipeline.preview import NewFrameCallback, PreviewFrame
from voxel.settings import ConfiguredDevice, SettingsBlock
from voxel.stage import SpecimenStage
from voxel.utils.log_config import get_component_logger, get_logger

if TYPE_CHECKING:
    from voxel.daq.tasks.wavegen import WaveGenTask


class BuildSpec(BaseModel):
    driver: str
    kwds: dict[str, Any] = {}


type BuildSpecGroup = dict[str, "BuildSpec"]


def parse_driver(driver: str) -> type:
    """Parse a driver string into a module and class name.
    :param driver: The driver string.
    :type driver: str
    :return: A tuple of the module and class name.
    :rtype: tuple[str, str]
    """
    module_name, class_name = driver.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    driver_class = getattr(module, class_name)
    if not isinstance(driver_class, type):
        raise TypeError(f"Attribute {class_name} in {module_name} is not a class.")
    return driver_class


def build_object(spec: "BuildSpec") -> Any:
    """Build an object from a build spec.
    :param spec: The build spec.
    :type spec: BuildSpec
    :return: The built object.
    :rtype: Any
    :raises TypeError: If the driver is not a class.
    """
    return parse_driver(spec.driver)(**spec.kwds)


def build_object_group(specs: BuildSpecGroup) -> dict[str, Any]:
    """Build a group of objects from a group of build specs.
    :param specs: The build specs.
    :type specs: dict[str, BuildSpec]
    :return: A dictionary of the built objects.
    :rtype: dict[str, Any]
    """
    built_objects = {}

    def build_single_object(name: str) -> None:
        if name in built_objects:
            return
        if spec := specs.get(name):
            kwds = spec.kwds.copy()
            for key, value in kwds.items():
                if isinstance(value, str) and value in specs:
                    build_single_object(value)
                    kwds[key] = built_objects[value]
            driver = parse_driver(spec.driver)
            if "name" in driver.__init__.__code__.co_varnames:
                kwds["name"] = name  # check if driver takes name as kwarg or arg
            built_objects[name] = driver(**kwds)

    for name in specs:
        build_single_object(name)
    return built_objects


class IOSpecs(BaseModel):
    writers: dict[str, BuildSpec]
    transfers: dict[str, BuildSpec] = {}


class PipelineOptions(BaseModel):
    type: Literal["local", "remote"]

    @property
    def is_local(self) -> bool:
        return self.type == "local"


class LocalPipelineOptions(PipelineOptions):
    type = "local"


class StageDefinition(BaseModel):
    x: str
    y: str
    z: str
    roll: str | None = None
    pitch: str | None = None
    yaw: str | None = None


class OpticalPathDefinition(BaseModel):
    aux_devices: list[str]


class IlluminationPathDefinition(OpticalPathDefinition):
    pass


class DetectionPathDefinition(OpticalPathDefinition):
    filter_wheels: list[str]
    pipeline: PipelineOptions = LocalPipelineOptions(type="local")


class InstrumentLayout(BaseModel):
    stage: StageDefinition
    detection: dict[str, DetectionPathDefinition]
    illumination: dict[str, IlluminationPathDefinition]


class InstrumentMetadata(BaseModel):
    name: str
    description: str | None = None
    version: str | None = None


class ChannelDefinition(BaseModel):
    name: str
    detection: str
    illumination: str
    filters: dict[str, str] = Field(default_factory=dict)


class InstrumentConfig(BaseModel):
    metadata: InstrumentMetadata
    io_specs: IOSpecs
    devices: BuildSpecGroup
    layout: InstrumentLayout
    channels: list[ChannelDefinition] = Field(default_factory=list)


class DetectionUnit:
    def __init__(
        self, pipeline: ICameraPipeline, filter_wheels: list[VoxelFilterWheel], aux_devices: list[VoxelDevice]
    ) -> None:
        self._pipeline = pipeline
        self._filter_wheels = {fw.name: fw for fw in filter_wheels}
        self._aux_devices = {device.name: device for device in aux_devices}
        self.log = get_component_logger(self)

    @property
    def pipeline(self) -> ICameraPipeline:
        return self._pipeline

    @property
    def camera(self) -> VoxelCamera | VoxelCameraProxy:
        return self._pipeline.camera

    @property
    def filter_wheels(self) -> dict[str, VoxelFilterWheel]:
        return self._filter_wheels

    @property
    def aux_devices(self) -> dict[str, VoxelDevice]:
        return self._aux_devices

    @property
    def devices(self) -> dict[str, VoxelDevice | VoxelCameraProxy]:
        """Return all devices in the detection unit."""
        return {**self.filter_wheels, **self.aux_devices, self.camera.name: self.camera}

    @property
    def name(self) -> str:
        return f"{self.camera.name} unit"

    def set_filters(self, filters: dict[str, str]) -> None:
        """Set the filters for the filter wheels in the detection unit."""
        for fw_name, filter_name in filters.items():
            if fw_name not in self.filter_wheels:
                raise ValueError(f"Filter wheel {fw_name} not found in detection unit {self.name}.")
            self.filter_wheels[fw_name].set_filter(filter_name)
            self.log.info(f"Set filter '{filter_name}' on filter wheel '{fw_name}' in detection unit '{self.name}'.")

    def validate_filters(self, filters: dict[str, str]) -> dict[str, str]:
        """Validate the filter assignments against the available filter wheels."""
        errors = []
        for wheel_name, filter_name in filters.items():
            if wheel_name not in self.filter_wheels:
                errors.append(f"Filter wheel '{wheel_name}' not found in the detection unit.")
            elif filter_name not in self.filter_wheels[wheel_name].filters.values():
                errors.append(f"Filter '{filter_name}' not found in filter wheel '{wheel_name}'.")

        if errors:
            raise ValueError("Invalid filter assignments:\n" + "\n".join(errors))
        return filters

    @classmethod
    def from_config(cls, camera_name: str, instrument: "Instrument") -> Self:
        """Create a DetectionUnit from a DetectionPathDefinition.
        Note: Assumes instrument devices and io_manager are already set up and that the layout is validated.
        :param camera_name: The name of the camera to use - must be in instrument's cameras.
        :type camera_name: str
        """
        definition = instrument.layout.detection[camera_name]
        camera = instrument.cameras.get(camera_name)
        if camera is None:
            raise ValueError(f"Camera {camera_name} not found in instrument {instrument.name}.")
        if isinstance(camera, VoxelCameraProxy):
            raise NotImplementedError(f"Camera {camera_name} uses a remote pipeline - currently unsupported.")
        pipeline = LocalCameraPipeline(camera=camera, io_manager=instrument.io_manager)

        filter_wheels = [instrument.filter_wheels[fw_name] for fw_name in definition.filter_wheels]
        aux_devices = [instrument.devices[device_name] for device_name in definition.aux_devices]
        return cls(pipeline=pipeline, filter_wheels=filter_wheels, aux_devices=aux_devices)


class IlluminationUnit:
    def __init__(self, laser: VoxelLaser, aux_devices: list[VoxelDevice]) -> None:
        self._laser = laser
        self._aux_devices = {device.name: device for device in aux_devices}
        self.log = get_component_logger(self)

    @property
    def laser(self) -> VoxelLaser:
        return self._laser

    @property
    def aux_devices(self) -> dict[str, VoxelDevice]:
        return self._aux_devices

    @property
    def devices(self) -> dict[str, VoxelDevice]:
        """Return all devices in the illumination unit."""
        return {**self.aux_devices, self.laser.name: self.laser}

    @property
    def name(self) -> str:
        return f"{self.laser.name} unit"

    def enable(self) -> None:
        """Enable the laser in the illumination unit."""
        self.laser.enable()

    def disable(self) -> None:
        """Disable the laser in the illumination unit."""
        self.laser.disable()

    @classmethod
    def from_config(cls, laser_name: str, instrument: "Instrument") -> Self:
        """Create a IlluminationUnit from an IlluminationPathDefinition.
        Note: Assumes instrument devices are already set up and that the layout is validated.
        :param laser_name: The name of the laser to use - must be in instrument's lasers.
        :type laser_name: str
        """
        definition = instrument.layout.illumination[laser_name]
        laser = instrument.lasers.get(laser_name)
        if laser is None:
            raise ValueError(f"Laser {laser_name} not found in instrument {instrument.name}.")
        aux_devices = [instrument.devices[device_name] for device_name in definition.aux_devices]
        return cls(laser=laser, aux_devices=aux_devices)


def wait_for_condition(condition_fn: Callable[[], bool], timeout: float, check_interval: float = 0.1) -> None:
    """Wait for a synchronous condition function to return True within the timeout."""
    start = time.monotonic()
    while True:
        if condition_fn():
            return
        if time.monotonic() - start > timeout:
            raise TimeoutError(f"Condition not met within {timeout} seconds")
        time.sleep(check_interval)


class ImagingStatus(StrEnum):
    INACTIVE = "inactive"
    STANDBY = "standby"
    PREVIEWING = "previewing"
    ACQUIRING = "acquiring"


class Channel:
    def __init__(
        self, name: str, detection: DetectionUnit, illumination: IlluminationUnit, filters: dict[str, str]
    ) -> None:
        self.name = name
        self.detection = detection
        self.illumination = illumination
        self.filters = self._validate_filter_assignments(filters, detection)
        self.status = ImagingStatus.INACTIVE
        self.log = get_component_logger(self)

    @property
    def is_busy(self) -> bool:
        """Check if the channel is currently busy (activated or previewing)."""
        return self.status in {ImagingStatus.STANDBY, ImagingStatus.PREVIEWING, ImagingStatus.ACQUIRING}

    def set_filters(self) -> None:
        """Set the filters for the channel's detection unit."""
        self.detection.set_filters(self.filters)
        self.log.info(f"Filters set for channel '{self.name}': {self.filters}")

    def start_preview(self, callback: NewFrameCallback) -> None:
        """
        Start the preview for the channel.
        - Set the filters in the detection unit in case they are not set.
        - Enable the illumination unit.
        - Start the preview in the detection pipeline. Ensure the pipeline is in INACTIVE state before starting.
        """
        self.log.info(f"Starting preview for channel '{self.name}'.")

        if self.detection.pipeline.state != PipelineStatus.INACTIVE:
            raise RuntimeError(
                f"Cannot start preview on channel '{self.name}' because the detection pipeline is not in INACTIVE state."
            )

        self.set_filters()
        self.illumination.enable()

        self.detection.pipeline.start_preview(callback)

        # wait for the pipeline to change to PREVIEWING state with a timeout
        def pipeline_is_previewing() -> bool:
            return self.detection.pipeline.state == PipelineStatus.PREVIEWING

        try:
            wait_for_condition(condition_fn=pipeline_is_previewing, timeout=5.0, check_interval=0.1)
            self.status = ImagingStatus.PREVIEWING
            self.log.info(f"Preview started for channel '{self.name}'.")
        except TimeoutError as e:
            self.log.error(f"Error starting preview for channel '{self.name}': {e}")
            raise RuntimeError("Failed to start channel preview as pipeline preview did not start successfully.")

    def stop_preview(self) -> None:
        """Stop the preview for the channel."""
        self.log.info(f"Stopping preview for channel '{self.name}'.")
        self.detection.pipeline.stop_preview()
        self.status = ImagingStatus.INACTIVE

    def prepare_stack_acquisition(self, config: StackAcquisitionConfig) -> list[range]:
        self.set_filters()
        return self.detection.pipeline.prepare_stack_acquisition(config)

    def acquire_batch(self, frame_range: range, on_new_frame: NewFrameCallback) -> None:
        """
        Acquire a batch of frames from the detection unit.
        :param frame_range: The range of frames to acquire.
        :param on_new_frame: Callback function to be called when a new frame is available.
        """
        self.detection.pipeline.acquire_batch(frame_range, on_new_frame=on_new_frame)

    @staticmethod
    def _validate_filter_assignments(filters: dict[str, str], detection: DetectionUnit) -> dict[str, str]:
        """
        Validate the filter assignments against the available filter wheels.
        Raise an error if any filter assignment is invalid.
        """
        try:
            return detection.validate_filters(filters)
        except ValueError as e:
            raise e


class Instrument:
    def __init__(
        self,
        metadata: InstrumentMetadata,
        devices: dict[str, VoxelDevice],
        layout: InstrumentLayout,
        io_manager: IOManager,
        channel_definitions: list[ChannelDefinition] = [],
    ) -> None:
        self.metadata = metadata
        self.log = get_component_logger(self)
        self._layout = self._validate_layout(devices=devices, layout=layout)
        self._devices = devices
        self._io_manager = io_manager

        self._stage = self._create_stage()
        self._detection: dict[str, DetectionUnit] = self._create_detection_units()
        self._illumination: dict[str, IlluminationUnit] = self._create_illumination_units()

        self._channels: dict[str, Channel] = {}
        for definition in channel_definitions:
            self.add_channel(definition)

        self._current_block: "ImagingBlock | None" = None

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def devices(self) -> dict[str, VoxelDevice]:
        return self._devices

    @property
    def layout(self) -> InstrumentLayout:
        return self._layout

    @property
    def stage(self) -> SpecimenStage:
        return self._stage

    @property
    def cameras(self) -> dict[str, VoxelCamera]:
        return {name: device for name, device in self.devices.items() if isinstance(device, VoxelCamera)}

    @property
    def filter_wheels(self) -> dict[str, VoxelFilterWheel]:
        return {name: device for name, device in self.devices.items() if isinstance(device, VoxelFilterWheel)}

    @property
    def lasers(self) -> dict[str, VoxelLaser]:
        return {name: device for name, device in self.devices.items() if isinstance(device, VoxelLaser)}

    @property
    def io_manager(self) -> IOManager:
        return self._io_manager

    @property
    def detection(self) -> dict[str, DetectionUnit]:
        return self._detection

    @property
    def illumination(self) -> dict[str, IlluminationUnit]:
        return self._illumination

    @property
    def current_block(self) -> "ImagingBlock | None":
        """Get the currently active imaging block."""
        return self._current_block

    def set_current_block(self, block: "ImagingBlock") -> None:
        """Set the current imaging block."""
        if self._current_block is not None:
            raise RuntimeError(f"Cannot set current block to '{block.name}' because another block is already active.")
        self._current_block = block
        self.log.info(f"Current imaging block set to '{block.name}'.")

    def reset_current_block(self) -> None:
        """Reset the current imaging block."""
        self._current_block = None

    def add_channel(self, definition: ChannelDefinition) -> None:
        """Add a channel to the instrument.
        :param name: The name of the channel.
        :type name: str
        :param definition: The channel definition.
        :type definition: ChannelDefinition
        """
        if definition.name in self._channels:
            raise ValueError(f"Channel '{definition.name}' already exists in instrument.")

        detection = self.detection.get(definition.detection)
        if detection is None:
            raise ValueError(f"Detection unit '{definition.detection}' not found in instrument.")
        illumination = self.illumination.get(definition.illumination)
        if illumination is None:
            raise ValueError(f"Illumination unit '{definition.illumination}' not found in instrument.")
        filters = definition.filters.copy()

        channel = Channel(name=definition.name, detection=detection, illumination=illumination, filters=filters)

        self._channels[definition.name] = channel
        self.log.info(f"Channel '{definition.name}' added.")

    def _create_detection_units(self) -> dict[str, DetectionUnit]:
        """Create the detection units for the instrument."""
        detection_units = {}
        for name, model in self._layout.detection.items():
            if model.pipeline.is_local:
                pipeline = LocalCameraPipeline(camera=self.cameras[name], io_manager=self.io_manager)
            else:
                raise NotImplementedError(f"Remote pipelines are not implemented yet for camera {name}")
            detection_units[name] = DetectionUnit(
                pipeline=pipeline,
                filter_wheels=[self.filter_wheels[fw_name] for fw_name in model.filter_wheels],
                aux_devices=[self.devices[device_name] for device_name in model.aux_devices],
            )
        return detection_units

    def _create_illumination_units(self) -> dict[str, IlluminationUnit]:
        """Create the illumination units for the instrument."""
        illumination_units = {}
        for name, model in self._layout.illumination.items():
            illumination_units[name] = IlluminationUnit(
                laser=self.lasers[name],
                aux_devices=[self.devices[device_name] for device_name in model.aux_devices],
            )
        return illumination_units

    def _create_stage(self) -> SpecimenStage:
        cfg = self.layout.stage
        # Mandatory linear axes
        x_ax_name, y_ax_name, z_ax_name = cfg.x, cfg.y, cfg.z
        x_axis, y_axis, z_axis = self.devices[x_ax_name], self.devices[y_ax_name], self.devices[z_ax_name]

        assert isinstance(x_axis, VoxelLinearAxis), f"Device '{x_ax_name}' for X axis is not a VoxelLinearAxis."
        assert isinstance(y_axis, VoxelLinearAxis), f"Device '{y_ax_name}' for Y axis is not a VoxelLinearAxis."
        assert isinstance(z_axis, VoxelLinearAxis), f"Device '{z_ax_name}' for Z axis is not a VoxelLinearAxis."

        # Optional rotational axes helper
        def get_rot_axis(axis_name_in_spec: str | None) -> VoxelRotationAxis | None:
            if axis_name_in_spec is None:
                return None
            device = self.devices[axis_name_in_spec]
            assert isinstance(
                device, VoxelRotationAxis
            ), f"Device '{axis_name_in_spec}' is not a VoxelRotationAxis, got {type(device).__name__}."
            return device

        roll_axis = get_rot_axis(cfg.roll)
        pitch_axis = get_rot_axis(cfg.pitch)
        yaw_axis = get_rot_axis(cfg.yaw)

        return SpecimenStage(x=x_axis, y=y_axis, z=z_axis, roll=roll_axis, pitch=pitch_axis, yaw=yaw_axis)

    @staticmethod
    def _validate_layout(devices: dict[str, VoxelDevice], layout: InstrumentLayout) -> InstrumentLayout:
        """Validate the assemblies configuration.
        :param devices: The devices.
        :type devices: dict[str, VoxelDevice]
        :param layout: The layout.
        :type layout: InstrumentLayout
        :return: Instrument layout that is validated.
        :rtype: InstrumentLayout
        """

        # Make sure all cameras have a valid detection layout
        for camera_name, camera in devices.items():
            if isinstance(camera, VoxelCamera) and camera_name not in layout.detection:
                raise ValueError(f"Camera {camera_name} does not have a valid detection layout.")

        # Make sure detection units have valid cameras and filter wheels and devices
        for unit_name, unit in layout.detection.items():
            if unit_name not in devices:
                raise ValueError(f"Camera/Detection unit {unit_name} not found in devices.")
            if not isinstance(devices[unit_name], VoxelCamera):
                raise TypeError(f"Camera/Detection unit {unit_name} is not a VoxelCamera.")

            for fw_name in unit.filter_wheels:
                if fw_name not in devices:
                    raise ValueError(f"Filter wheel {fw_name} of detection unit {unit_name} not found in devices.")
                if not isinstance(devices[fw_name], VoxelFilterWheel):
                    raise TypeError(f"Device {fw_name} of detection unit {unit_name} is not a VoxelFilterWheel.")

        # Make sure all lasers have a valid illumination path unit
        for laser_name, laser in devices.items():
            if isinstance(laser, VoxelLaser) and laser_name not in layout.illumination:
                raise ValueError(f"Laser {laser_name} does not have a valid illumination path unit.")

        # Make sure illumination units have valid lasers
        for unit_name, unit in layout.illumination.items():
            if unit_name not in devices:
                raise ValueError(f"Laser/Illumination unit {unit_name} not found in devices.")
            if not isinstance(devices[unit_name], VoxelLaser):
                raise TypeError(f"Laser/Illumination unit {unit_name} is not a VoxelLaser.")

        stage_axes = list(layout.stage.model_dump().values())

        # Combined check of devices array in the layout
        for unit_name, unit in list(layout.detection.items()) + list(layout.illumination.items()):
            for device_name in unit.aux_devices:
                if device_name not in devices:
                    raise ValueError(f"Device {device_name} of unit {unit_name} not found in devices.")
                if not isinstance(devices[device_name], VoxelDevice):
                    raise TypeError(f"Device {device_name} of unit {unit_name} is not a VoxelDevice.")
                if device_name in stage_axes:
                    raise ValueError(
                        f"Device {device_name} of unit {unit_name} is a stage axis and cannot be in an optical path."
                    )

        return layout

    @classmethod
    def from_config(cls, config: InstrumentConfig) -> Self:
        """Load an instrument from a config."""
        instrument = cls(
            metadata=config.metadata,
            io_manager=IOManager(config.io_specs),
            devices=build_object_group(config.devices),
            layout=config.layout,
            channel_definitions=config.channels,
        )

        return instrument

    @classmethod
    def from_yaml(cls, path: str | Path) -> Self:
        """Load an instrument from a YAML file.
        :param path: The path to the YAML file.
        :type path: str | Path
        :return: The loaded instrument.
        :rtype: Instrument
        """
        from ruamel.yaml import YAML

        yaml = YAML()
        with open(path, "r") as f:
            config = InstrumentConfig.model_validate(yaml.load(f))
        return cls.from_config(config)


class ImagingBlockDefinition(BaseModel):
    """Serializable definition for an imaging block."""

    channels: list[str]
    settings: dict[str, SettingsBlock] = Field(default_factory=dict)
    description: str | None = None


class ImagingBlock:
    """
    A collection of instrument devices that are concurrently used for imaging.
    Consists of one or multiple channels where each channel uses a distinct detection and illumination unit.
    """

    def __init__(self, name: str, definition: ImagingBlockDefinition, instrument: Instrument):
        self.name = name
        self.log = get_logger(f"{self.__class__.__name__}({self.name})")
        self._definition = definition
        self._instrument = instrument

        self._status = ImagingStatus.INACTIVE

        # resolve channels from the block definition
        self._channels = self.resolve_channels(definition, instrument)
        self._preview_callbacks: set[NewFrameCallback] = set()

        # resolve devices for the block into a dictionary of ConfiguredDevice
        self._configured_devices: dict[str, ConfiguredDevice] = {}
        for channel in self._channels.values():
            for unit in (channel.detection, channel.illumination):
                for device_name, device in unit.devices.items():
                    if device_name not in self._configured_devices:
                        self._configured_devices[device_name] = ConfiguredDevice(
                            device=device,
                            settings=self._definition.settings.get(device_name),
                        )

        # TODO: implement imaging task as a collection of WaveGenChannels / ao ports
        self.imaging_task: WaveGenTask

    def apply_settings(self, current_z: float | None) -> None:
        """Apply appropriate settings to all devices in the block based on the z position."""
        for configured_device in self._configured_devices.values():
            if configured_device.settings:
                configured_device.apply_settings(current_z)
            else:
                self.log.warning(
                    f"No settings found for device '{configured_device.device.name}' in block '{self.name}'."
                )

    def activate(self) -> None:
        """Activate the block and set as current block in the instrument."""
        self.log.info(f"Activating block '{self.name}' with {len(self._channels)} channels.")
        if self._instrument.current_block is not None:
            raise RuntimeError(
                f"Cannot activate block '{self.name}' because another block"
                f" '{self._instrument.current_block.name}' is already active."
            )
        for channel in self._channels.values():
            channel.set_filters()
        self.apply_settings(self._instrument.stage.position_mm.z)
        self._instrument.set_current_block(self)
        self._status = ImagingStatus.STANDBY
        self.log.info(f"Block '{self.name}' activated.")

    def deactivate(self) -> None:
        if self._status == ImagingStatus.ACQUIRING:
            raise RuntimeError(f"Cannot deactivate block '{self.name}' while it is acquiring data.")
        if self._status == ImagingStatus.PREVIEWING:
            self.stop_preview()
        self._status = ImagingStatus.INACTIVE
        self._instrument.reset_current_block()

    def start_preview(self) -> None:
        self.log.info(f"Starting preview for block '{self.name}' with {len(self._channels)} channels.")

        # TODO: setup imaging task and start it

        for channel in self._channels.values():
            channel.start_preview(self._notify_preview_callbacks)

        self._status = ImagingStatus.PREVIEWING

    def stop_preview(self) -> None:
        """Stop the preview for all channels in the block."""
        self.log.info(f"Stopping preview for block '{self.name}'.")

        # TODO: stop imaging task
        for channel in self._channels.values():
            channel.stop_preview()

        self._status = ImagingStatus.STANDBY

    def acquire_stack(self, config: StackAcquisitionConfig) -> None:
        """
        Prepare all channels for stack acquisition and get the frame ranges.
        Ensure that all channels have the same frame ranges.
        All channels need to be acquired in parallel.
        :param config: The stack acquisition configuration.
        :type config: StackAcquisitionConfig
        """

    def prepare_stack_acquisition(self, config: StackAcquisitionConfig) -> list[range]:
        """
        ** Might end up being deprecated in favor of `acquire_stack` **
        Prepare the block for acquisition.
        This method should be called before starting the acquisition.
        It prepares the imaging task and returns the ranges for each channel.
        """
        self.log.info(f"Preparing acquisition for block '{self.name}' with config: {config}")
        if self._status == ImagingStatus.ACQUIRING:
            raise RuntimeError("Cannot prepare acquisition while an acquisition is already in progress.")
        if self._status == ImagingStatus.PREVIEWING:
            self.stop_preview()
        frame_ranges = {}
        for channel in self._channels.values():
            frame_ranges[channel.name] = channel.prepare_stack_acquisition(config)

        # check if all channels have the same frame ranges
        num_frames_per_channel = {name: len(r) for name, r in frame_ranges.items()}
        if len(set(num_frames_per_channel.values())) != 1:
            error_message_lines = ["All channels must have the same number of frames for acquisition."]
            for name, num_frames in num_frames_per_channel.items():
                error_message_lines.append(f"  Channel '{name}': {num_frames} frames")
            raise ValueError("\n".join(error_message_lines))
        self._status = ImagingStatus.ACQUIRING
        return next(iter(frame_ranges.values()))  # return the frame range of the first channel

    def acquire_batch(self, frame_range: range, on_new_frame: NewFrameCallback) -> None: ...

    def acquire_stack__older(self, config: "StackAcquisitionConfig") -> None:
        """
        ** This is from an older version of the code where we only had a single channel. **
        Perform stack acquisition:
          1. Configure the NI-DAQ task (imaging_task) with appropriate waveforms
             and adjust the trigger frequency based on the camera's frame rate.
          2. Prepare the engine for acquisition (which configures the writer and waits for disk space)
             and obtain the frame ranges.
          3. Start the main imaging_task.
          4. For each batch: configure and start the trigger task for the number of frames,
             delegate frame acquisition to the engine, and then stop the trigger.
          5. Stop the imaging_task and finalize acquisition via the engine.
        """

        self.log.info("Starting stack acquisition.")

        def acquisition_thread():
            # Configure NI-DAQ task for acquisition.
            self.imaging_task.regenerate_waveforms()
            self.imaging_task.write()

            # Adjust trigger frequency based on camera frame rate.
            self.imaging_task.trigger_task.freq_hz = self.detection.pipeline.frame_rate_hz * 0.75

            # Prepare the engine for acquisition and get frame ranges.
            frame_ranges = self.detection.pipeline.prepare_stack_acquisition(config)

            self.imaging_task.start()
            for frame_range in frame_ranges:
                self.imaging_task.trigger_task.configure(num_samples=len(frame_range))
                self.imaging_task.trigger_task.start()
                # Acquire the current batch with the engine.
                self.detection.pipeline.acquire_batch(frame_range, on_new_frame=self._notify_preview_callbacks)
                self.imaging_task.trigger_task.stop()
            self.imaging_task.stop()
            self.detection.pipeline.finalize_stack_acquisition()
            self.log.info("Stack acquisition complete.")

        threading.Thread(target=acquisition_thread, daemon=True).start()

    def register_preview_callback(self, callback: NewFrameCallback) -> None:
        """
        Register a callback to be called when a new preview frame is available.
        The callback should accept a single argument, which will be the new frame.
        """
        self._preview_callbacks.add(callback)

    def unregister_preview_callback(self, callback: NewFrameCallback) -> None:
        """Unregister a previously registered preview callback."""
        self._preview_callbacks.discard(callback)

    def _notify_preview_callbacks(self, frame: PreviewFrame) -> None:
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
    def resolve_channels(definition: ImagingBlockDefinition, instrument: Instrument) -> dict[str, Channel]:
        """Resolve channels from the block definition."""
        channels = {}
        for channel_name in definition.channels:
            if channel_name not in instrument._channels:
                raise ValueError(f"Channel '{channel_name}' not found in instrument.")
            channels[channel_name] = instrument._channels[channel_name]
        return channels

    def _resolve_devices(self) -> dict[str, ConfiguredDevice]:
        """Resolve all devices used in the block."""
        devices = {}

        def add_unit_devices(unit: IlluminationUnit | DetectionUnit) -> None:
            for device_name, device in unit.devices.items():
                if device_name not in devices:
                    devices[device_name] = ConfiguredDevice(
                        device=device,
                        settings=self._definition.settings.get(device_name),
                    )

        for channel in self._channels.values():
            add_unit_devices(channel.detection)
            add_unit_devices(channel.illumination)

        return devices


class ImagingPlanDefinition(BaseModel):
    """Serializable definition for an imaging plan."""

    name: str
    description: str | None = None
    blocks: list[ImagingBlockDefinition] = Field(default_factory=list)


class ImagingPresets(BaseModel):
    """Serializable definition for imaging presets."""

    blocks: dict[str, ImagingBlockDefinition]
    plans: list[ImagingPlanDefinition]

    @model_validator(mode="after")
    def validate_plans(self) -> Self:
        """Validate that all blocks referenced in plans exist."""
        for plan in self.plans:
            for block_name in plan.blocks:
                if block_name not in self.blocks:
                    raise ValueError(f"Plan '{plan.name}' references non-existent block: {block_name}")
        return self

    def validate_blocks(self, instrument: Instrument) -> None:
        """Validate that all blocks are compatible with the instrument."""
        for block in self.blocks.values():
            for channel_name in block.channels:
                if channel_name not in instrument._channels:
                    raise ValueError(f"Block '{block.description}' references non-existent channel: {channel_name}")
