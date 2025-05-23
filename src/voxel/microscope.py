from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field

from voxel.detection_path import FilterWheel
from voxel.devices.base import VoxelDevice
from voxel.devices.camera import VoxelCamera
from voxel.devices.laser import VoxelLaser
from voxel.devices.linear_axis import VoxelLinearAxis
from voxel.devices.rotation_axis import VoxelRotationAxis
from voxel.pipeline.io.manager import IOManager
from voxel.stage import SpecimenStage
from voxel.utils.log_config import get_component_logger


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


class StageConfig(BaseModel):
    x: str
    y: str
    z: str
    roll: str | None = None
    pitch: str | None = None
    yaw: str | None = None


class OpticalPathAssembly(BaseModel):
    devices: list[str]


class IlluminationAssembly(OpticalPathAssembly):
    pass


class PipelineSpecs(BaseModel):
    type: Literal["local", "remote"]

    @property
    def is_local(self) -> bool:
        return self.type == "local"


class LocalCameraPipelineSpecs(PipelineSpecs):
    type = "local"


class DetectionAssembly(OpticalPathAssembly):
    filter_wheels: list[str]
    pipeline: PipelineSpecs = LocalCameraPipelineSpecs(type="local")


class AssembliesModel(BaseModel):
    detection: dict[str, DetectionAssembly]
    illumination: dict[str, IlluminationAssembly]


class ChannelRecipeModel(BaseModel):
    detection: str
    illumination: str
    settings: dict[str, Any] = Field(default_factory=dict)


class InstrumentMetadata(BaseModel):
    name: str
    description: str | None = None
    version: str | None = None


class InstrumentConfig(BaseModel):
    metadata: InstrumentMetadata
    devices: BuildSpecGroup
    assemblies: AssembliesModel
    stage: StageConfig
    io_specs: IOSpecs
    channels: dict[str, ChannelRecipeModel]


class Instrument:
    def __init__(
        self,
        metadata: InstrumentMetadata,
        devices: dict[str, VoxelDevice],
        assemblies: AssembliesModel,
        stage_specs: StageConfig,
        io_manager: IOManager,
    ) -> None:
        self.log = get_component_logger(self)
        self.stage = self._create_stage(devices=devices, stage_specs=stage_specs)
        self.validate_assembly(devices=devices, assemblies=assemblies, stage=self.stage)
        self.metadata = metadata
        self.devices = devices
        self.assemblies = assemblies
        self.io_manager = io_manager
        self.channels: dict[str, Channel] = {}

    @property
    def cameras(self) -> dict[str, VoxelCamera]:
        """Get the cameras in the instrument."""
        return {name: device for name, device in self.devices.items() if isinstance(device, VoxelCamera)}

    @property
    def lasers(self) -> dict[str, VoxelLaser]:
        """Get the lasers in the instrument."""
        return {name: device for name, device in self.devices.items() if isinstance(device, VoxelLaser)}

    @property
    def filter_wheels(self) -> dict[str, FilterWheel]:
        """Get the filter wheels in the instrument."""
        return {name: device for name, device in self.devices.items() if isinstance(device, FilterWheel)}

    def get_channel_builder(self) -> "ChannelBuilder":
        """Get a channel builder for the instrument."""
        return ChannelBuilder(self)

    def add_channel(self, channel: "Channel") -> None:
        """Add a channel to the instrument."""
        if channel.name in self.channels:
            if self.channels[channel.name] is channel:
                return
            self.log.warning(f"Channel {channel.name} already exists. Overwriting.")
        self.channels[channel.name] = channel

    @classmethod
    def from_config(cls, config: InstrumentConfig) -> Self:
        """Load an instrument from a config."""
        instrument = cls(
            metadata=config.metadata,
            devices=build_object_group(config.devices),
            assemblies=config.assemblies,
            stage_specs=config.stage,
            io_manager=IOManager(config.io_specs),
        )
        for channel_name, channel_recipe in config.channels.items():
            builder = instrument.get_channel_builder()
            builder.set_name(channel_name)
            builder.set_detection(channel_recipe.detection)
            builder.set_illumination(channel_recipe.illumination)
            for fw_name, filter_name in channel_recipe.settings.items():
                builder.configure_filter_wheel(fw_name, filter_name)
            builder.build()
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

    @staticmethod
    def validate_assembly(devices: dict[str, VoxelDevice], assemblies: AssembliesModel, stage: SpecimenStage) -> None:
        """Validate the assemblies configuration.
        :param devices: The devices.
        :type devices: dict[str, VoxelDevice]
        :param assemblies: The assemblies.
        :type assemblies: AssembliesModel
        """

        # Make sure all cameras have a valid detection assembly
        for camera_name, camera in devices.items():
            if isinstance(camera, VoxelCamera) and camera_name not in assemblies.detection:
                raise ValueError(f"Camera {camera_name} does not have a valid detection assembly.")

        # Make sure detection assemblies have valid cameras and filter wheels and devices
        for assembly_name, assembly in assemblies.detection.items():
            if assembly_name not in devices:
                raise ValueError(f"Camera/Assembly {assembly_name} not found in devices.")
            if not isinstance(devices[assembly_name], VoxelCamera):
                raise TypeError(f"Camera/Assembly {assembly_name} is not a VoxelCamera.")

            for fw_name in assembly.filter_wheels:
                if fw_name not in devices:
                    raise ValueError(f"Filter wheel {fw_name} of assembly {assembly_name} not found in devices.")
                if not isinstance(devices[fw_name], FilterWheel):
                    raise TypeError(f"Device {fw_name} of assembly {assembly_name} is not a FilterWheel.")

        # Make sure all lasers have a valid illumination assembly
        for laser_name, laser in devices.items():
            if isinstance(laser, VoxelLaser) and laser_name not in assemblies.illumination:
                raise ValueError(f"Laser {laser_name} does not have a valid illumination assembly.")

        # Make sure illumination assemblies have valid lasers
        for assembly_name, assembly in assemblies.illumination.items():
            if assembly_name not in devices:
                raise ValueError(f"Laser/Assembly {assembly_name} not found in devices.")
            if not isinstance(devices[assembly_name], VoxelLaser):
                raise TypeError(f"Laser/Assembly {assembly_name} is not a VoxelLaser.")

        stage_linear_axes = [stage.x.name, stage.y.name, stage.z.name]
        stage_rotation_axes = [axis.name for axis in [stage.roll, stage.pitch, stage.yaw] if axis is not None]
        stage_axes = stage_linear_axes + stage_rotation_axes

        # Combined check of devices array in the assemblies
        for assembly_name, assembly in list(assemblies.detection.items()) + list(assemblies.illumination.items()):
            for device_name in assembly.devices:
                if device_name not in devices:
                    raise ValueError(f"Device {device_name} of assembly {assembly_name} not found in devices.")
                if not isinstance(devices[device_name], VoxelDevice):
                    raise TypeError(f"Device {device_name} of assembly {assembly_name} is not a VoxelDevice.")
                if device_name in stage_axes:
                    raise ValueError(
                        f"Device {device_name} of assembly {assembly_name} is a stage axis and cannot be in an assembly."
                    )

    @staticmethod
    def _create_stage(devices: dict[str, VoxelDevice], stage_specs: StageConfig) -> SpecimenStage:
        """Create a stage from the devices and stage specs.
        :param devices: The devices.
        :type devices: dict[str, VoxelDevice]
        :param stage_specs: The stage specs.
        :type stage_specs: SpecimenStageSpecs
        :return: The created stage.
        :rtype: SpecimenStage
        """
        # Mandatory linear axes
        x_ax_name, y_ax_name, z_ax_name = stage_specs.x, stage_specs.y, stage_specs.z
        x_axis, y_axis, z_axis = devices[x_ax_name], devices[y_ax_name], devices[z_ax_name]

        assert isinstance(x_axis, VoxelLinearAxis), f"Device '{x_ax_name}' for X axis is not a VoxelLinearAxis."
        assert isinstance(y_axis, VoxelLinearAxis), f"Device '{y_ax_name}' for Y axis is not a VoxelLinearAxis."
        assert isinstance(z_axis, VoxelLinearAxis), f"Device '{z_ax_name}' for Z axis is not a VoxelLinearAxis."

        # Optional rotational axes helper
        def get_rot_axis(axis_name_in_spec: str | None) -> VoxelRotationAxis | None:
            if axis_name_in_spec is None:
                return None
            device = devices[axis_name_in_spec]
            assert isinstance(
                device, VoxelRotationAxis
            ), f"Device '{axis_name_in_spec}' is not a VoxelRotationAxis, got {type(device).__name__}."
            return device

        roll_axis = get_rot_axis(stage_specs.roll)
        pitch_axis = get_rot_axis(stage_specs.pitch)
        yaw_axis = get_rot_axis(stage_specs.yaw)

        return SpecimenStage(x=x_axis, y=y_axis, z=z_axis, roll=roll_axis, pitch=pitch_axis, yaw=yaw_axis)


class DeviceSetting:
    pass


@dataclass
class DeviceSettingsBlock:
    def add(self, entry: DeviceSetting): ...
    def merge(self, priority: Self) -> Self:
        """Merge two settings blocks.
        :param priority: The higher priority settings block.
        :type priority: DeviceSettingsBlock
        :return: The merged settings block.
        :rtype: DeviceSettingsBlock
        """
        return self


@dataclass
class ChannelDevices:
    detection: dict[str, VoxelDevice]
    illumination: dict[str, VoxelDevice]


class ChannelFilterWheelSetting:
    wheel: FilterWheel
    filter: str


class ChannelAssemblyInfo:
    detection: DetectionAssembly
    illumination: IlluminationAssembly


@dataclass
class Channel:
    name: str
    camera: VoxelCamera
    laser: VoxelLaser
    filter_wheels: dict[str, tuple[FilterWheel, str]]
    devices: dict[str, VoxelDevice]
    settings: DeviceSettingsBlock


class ChannelBuilder:
    def __init__(self, instrument: Instrument):
        self.instrument = instrument
        self._reset_state()

    @property
    def detection_assemblies(self) -> dict[str, DetectionAssembly]:
        """Get the detection assemblies in the instrument."""
        return self.instrument.assemblies.detection

    @property
    def illumination_assemblies(self) -> dict[str, IlluminationAssembly]:
        """Get the illumination assemblies in the instrument."""
        return self.instrument.assemblies.illumination

    def _reset_state(self) -> None:
        """Initializes or resets the builder's internal state."""
        self._channel_name: str | None = None
        self._camera: VoxelCamera | None = None
        self._laser: VoxelLaser | None = None
        self._fw_settings: dict[str, tuple[FilterWheel, str]] = {}  # {fw_name: (fw_obj, filter_name)}
        self._aux_devices: dict[str, VoxelDevice] = {}  # Auxiliary devices from assemblies
        self._detection_assembly: DetectionAssembly | None = None
        self._illumination_assembly: IlluminationAssembly | None = None
        # Potentially other settings for the channel
        self._channel_specific_settings: DeviceSettingsBlock = DeviceSettingsBlock()

    def set_name(self, name: str) -> Self:
        """Sets the name for the channel being built."""
        if not name:
            raise ValueError("Channel name cannot be empty.")
        # Could add more validation for name format if needed
        self._channel_name = name
        return self

    def set_detection(self, camera_name: str) -> Self:
        """
        Sets the detection path for the channel using the specified camera.
        This also loads associated filter wheels and auxiliary devices from the assembly.
        """
        if camera_name not in self.instrument.devices:
            raise ValueError(f"Camera '{camera_name}' not found in instrument devices.")
        camera = self.instrument.devices[camera_name]
        if not isinstance(camera, VoxelCamera):
            raise TypeError(f"Device '{camera_name}' is not a VoxelCamera.")

        assembly = self.instrument.assemblies.detection.get(camera_name)
        if not assembly:
            raise ValueError(f"No detection assembly defined for camera '{camera_name}'.")

        self._camera = camera
        self._detection_assembly = assembly
        # Automatically add auxiliary devices from this assembly
        self._add_aux_devices(assembly.devices)
        # Clear any previous filter wheel settings if detection assembly changes
        self._fw_settings = {}
        print(f"Detection assembly set to '{camera_name}'. Available filter wheels: {assembly.filter_wheels}")
        return self

    def configure_filter_wheel(self, fw_name: str, filter_name: str) -> Self:
        """Configures a specific filter for a filter wheel in the current detection assembly."""
        if not self._detection_assembly:
            raise ValueError("Detection assembly must be set before configuring filter wheels.")
        if fw_name not in self._detection_assembly.filter_wheels:
            raise ValueError(
                f"Filter wheel '{fw_name}' is not part of the current detection assembly "
                f"for camera '{self._camera.name if self._camera else 'N/A'}'. "
                f"Available in assembly: {self._detection_assembly.filter_wheels}"
            )

        fw_device = self.instrument.filter_wheels.get(fw_name)
        if not fw_device:
            # This should ideally not happen if assemblies are validated against devices
            raise ValueError(f"Filter wheel device '{fw_name}' not found in instrument.filter_wheels.")

        if filter_name not in fw_device.filters.values():
            raise ValueError(
                f"Filter '{filter_name}' not found in filter wheel '{fw_name}'. "
                f"Available filters: {list(fw_device.filters.values())}"
            )

        self._fw_settings[fw_name] = (fw_device, filter_name)
        print(f"Filter wheel '{fw_name}' configured to use filter '{filter_name}'.")
        return self

    def set_illumination(self, laser_name: str) -> Self:
        """
        Sets the illumination path for the channel using the specified laser.
        This also loads associated auxiliary devices from the assembly.
        """
        if laser_name not in self.instrument.devices:
            raise ValueError(f"Laser '{laser_name}' not found in instrument devices.")
        laser = self.instrument.devices[laser_name]
        if not isinstance(laser, VoxelLaser):
            raise TypeError(f"Device '{laser_name}' is not a VoxelLaser.")

        assembly = self.instrument.assemblies.illumination.get(laser_name)
        if not assembly:
            raise ValueError(f"No illumination assembly defined for laser '{laser_name}'.")

        self._laser = laser
        self._illumination_assembly = assembly
        # Automatically add auxiliary devices from this assembly
        self._add_aux_devices(assembly.devices)
        print(f"Illumination assembly set to '{laser_name}'.")
        return self

    def _add_aux_devices(self, device_names: list[str]) -> None:
        """Helper to add auxiliary devices to the channel's device list."""
        for dev_name in device_names:
            if dev_name in self.instrument.devices:
                device = self.instrument.devices[dev_name]
                # Avoid re-adding the main camera/laser if they are somehow listed in aux devices
                if (self._camera and dev_name == self._camera.name) or (self._laser and dev_name == self._laser.name):
                    continue
                self._aux_devices[dev_name] = device
            else:
                # This should be caught by assembly validation earlier, but as a safeguard:
                raise ValueError(f"Auxiliary device '{dev_name}' from assembly not found in instrument devices.")

    def add_setting(self, device_setting: DeviceSetting) -> Self:
        """Adds a generic device setting block for the channel (more advanced)."""
        self._channel_specific_settings.add(device_setting)  # Assuming DeviceSettingsBlock has an add method
        return self

    def build(self) -> Channel:
        """
        Validates the current configuration, builds the Channel object,
        adds it to the instrument, and returns the created Channel.
        Resets the builder afterwards for a new channel definition.
        """
        if not self._channel_name:
            raise ValueError("Channel name must be set.")
        if not self._camera or not self._detection_assembly:
            raise ValueError("Detection assembly (camera) must be set.")
        if not self._laser or not self._illumination_assembly:
            raise ValueError("Illumination assembly (laser) must be set.")

        # Validate all filter wheels in the selected detection assembly are configured
        for fw_name_in_assembly in self._detection_assembly.filter_wheels:
            if fw_name_in_assembly not in self._fw_settings:
                raise ValueError(
                    f"Filter wheel '{fw_name_in_assembly}' (part of detection assembly) "
                    "has not been configured with a filter selection."
                )

        # Consolidate all unique auxiliary devices
        # (already handled by _aux_devices being a dict)

        channel = Channel(
            name=self._channel_name,
            camera=self._camera,
            laser=self._laser,
            filter_wheels=self._fw_settings.copy(),  # Pass copies
            devices=self._aux_devices.copy(),
            settings=self._channel_specific_settings,  # Or a copy if it's mutable
        )

        self.instrument.add_channel(channel)  # Adds to the instrument's dictionary

        # Store a reference to the built channel before resetting, for return
        built_channel = self.instrument.channels[self._channel_name]

        self._reset_state()
        print(f"Channel '{channel.name}' successfully built and added to instrument.")
        return built_channel

    def get_current_config_summary(self) -> str:
        """Provides a summary of the channel being built (useful for UI/interactive)."""
        summary = []
        summary.append(f"Building Channel: {self._channel_name or 'Not Set'}")
        summary.append(f"  Camera: {self._camera.name if self._camera else 'Not Set'}")
        if self._detection_assembly:
            summary.append(f"    Detection Assembly Filter Wheels: {self._detection_assembly.filter_wheels}")
            summary.append(f"    Configured Filters: { {fw: filt for fw, (_, filt) in self._fw_settings.items()} }")
        summary.append(f"  Laser: {self._laser.name if self._laser else 'Not Set'}")
        summary.append(f"  Auxiliary Devices: {list(self._aux_devices.keys())}")
        return "\n".join(summary)
