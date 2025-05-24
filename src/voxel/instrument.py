from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field

from voxel.channel_builder import ChannelBuilder
from voxel.devices.filter_wheel import VoxelFilterWheel
from voxel.devices.base import VoxelDevice
from voxel.devices.camera import VoxelCamera
from voxel.devices.laser import VoxelLaser
from voxel.devices.linear_axis import VoxelLinearAxis
from voxel.devices.rotation_axis import VoxelRotationAxis
from voxel.pipeline.interface import ICameraPipeline
from voxel.pipeline.io.manager import IOManager
from voxel.pipeline.local import LocalCameraPipeline
from voxel.settings import SettingsBlock
from voxel.stage import SpecimenStage
from voxel.channel import ImagingChannel
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


class OpticalPathUnit(BaseModel):
    aux_devices: list[str]


class IlluminationUnitModel(OpticalPathUnit):
    pass


class PipelineOptions(BaseModel):
    type: Literal["local", "remote"]

    @property
    def is_local(self) -> bool:
        return self.type == "local"


class LocalPipelineOptions(PipelineOptions):
    type = "local"


class DetectionUnitModel(OpticalPathUnit):
    filter_wheels: list[str]
    pipeline: PipelineOptions = LocalPipelineOptions(type="local")


class InstrumentAssembly(BaseModel):
    stage: StageConfig
    detection: dict[str, DetectionUnitModel]
    illumination: dict[str, IlluminationUnitModel]


class ChannelConfiguration(BaseModel):
    detection: str
    illumination: str
    filters: dict[str, str] = Field(default_factory=dict)
    settings: dict[str, SettingsBlock] = Field(default_factory=dict)


class InstrumentMetadata(BaseModel):
    name: str
    description: str | None = None
    version: str | None = None


class InstrumentConfig(BaseModel):
    metadata: InstrumentMetadata
    devices: BuildSpecGroup
    assembly: InstrumentAssembly
    io_specs: IOSpecs
    channels: dict[str, ChannelConfiguration]


class Instrument:
    def __init__(
        self,
        metadata: InstrumentMetadata,
        devices: dict[str, VoxelDevice],
        assembly: InstrumentAssembly,
        io_manager: IOManager,
    ) -> None:
        self.log = get_component_logger(self)
        self.validate_assembly(devices=devices, assembly=assembly)
        self.metadata = metadata
        self._devices = devices
        self._assembly = assembly
        self._io_manager = io_manager
        self._stage = self._create_stage()
        self._pipelines = self._create_pipelines()
        self._channels: dict[str, ImagingChannel] = {}

    @property
    def devices(self) -> dict[str, VoxelDevice]:
        return self._devices

    @property
    def assembly(self) -> InstrumentAssembly:
        return self._assembly

    @property
    def stage(self) -> SpecimenStage:
        return self._stage

    @property
    def cameras(self) -> dict[str, VoxelCamera]:
        return {name: device for name, device in self.devices.items() if isinstance(device, VoxelCamera)}

    @property
    def pipelines(self) -> dict[str, ICameraPipeline]:
        return self._pipelines

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
    def channels(self) -> dict[str, ImagingChannel]:
        return self._channels

    def _create_pipelines(self) -> dict[str, ICameraPipeline]:
        """Create the pipelines for the cameras in the instrument."""
        pipelines = {}
        for camera_name, camera in self.cameras.items():
            detection_unit = self.assembly.detection.get(camera_name)
            if detection_unit and detection_unit.pipeline.is_local:
                pipeline = LocalCameraPipeline(camera=camera, io_manager=self.io_manager)
            else:
                raise NotImplementedError(
                    f"Remote pipelines are not implemented yet for camera {camera_name} with assembly {detection_unit}"
                )
            pipelines[camera_name] = pipeline
        return pipelines

    def _create_stage(self) -> SpecimenStage:
        cfg = self.assembly.stage
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

    @classmethod
    def from_config(cls, config: InstrumentConfig) -> Self:
        """Load an instrument from a config."""
        instrument = cls(
            metadata=config.metadata,
            devices=build_object_group(config.devices),
            assembly=config.assembly,
            io_manager=IOManager(config.io_specs),
        )
        for channel_name, channel_recipe in config.channels.items():
            builder = instrument.get_channel_builder()
            builder.set_name(channel_name)
            builder.set_detection(channel_recipe.detection)
            builder.set_illumination(channel_recipe.illumination)
            for fw_name, filter_name in channel_recipe.filters.items():
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
    def validate_assembly(devices: dict[str, VoxelDevice], assembly: InstrumentAssembly) -> None:
        """Validate the assemblies configuration.
        :param devices: The devices.
        :type devices: dict[str, VoxelDevice]
        :param assemblies: The assemblies.
        :type assemblies: InstrumentAssembly
        """

        # Make sure all cameras have a valid detection assembly
        for camera_name, camera in devices.items():
            if isinstance(camera, VoxelCamera) and camera_name not in assembly.detection:
                raise ValueError(f"Camera {camera_name} does not have a valid detection assembly.")

        # Make sure detection assemblies have valid cameras and filter wheels and devices
        for unit_name, unit in assembly.detection.items():
            if unit_name not in devices:
                raise ValueError(f"Camera/Assembly {unit_name} not found in devices.")
            if not isinstance(devices[unit_name], VoxelCamera):
                raise TypeError(f"Camera/Assembly {unit_name} is not a VoxelCamera.")

            for fw_name in unit.filter_wheels:
                if fw_name not in devices:
                    raise ValueError(f"Filter wheel {fw_name} of assembly {unit_name} not found in devices.")
                if not isinstance(devices[fw_name], VoxelFilterWheel):
                    raise TypeError(f"Device {fw_name} of assembly {unit_name} is not a VoxelFilterWheel.")

        # Make sure all lasers have a valid illumination assembly
        for laser_name, laser in devices.items():
            if isinstance(laser, VoxelLaser) and laser_name not in assembly.illumination:
                raise ValueError(f"Laser {laser_name} does not have a valid illumination assembly.")

        # Make sure illumination assemblies have valid lasers
        for unit_name, unit in assembly.illumination.items():
            if unit_name not in devices:
                raise ValueError(f"Laser/Assembly {unit_name} not found in devices.")
            if not isinstance(devices[unit_name], VoxelLaser):
                raise TypeError(f"Laser/Assembly {unit_name} is not a VoxelLaser.")

        stage_axes = list(assembly.stage.model_dump().values())

        # Combined check of devices array in the assemblies
        for unit_name, unit in list(assembly.detection.items()) + list(assembly.illumination.items()):
            for device_name in unit.aux_devices:
                if device_name not in devices:
                    raise ValueError(f"Device {device_name} of assembly {unit_name} not found in devices.")
                if not isinstance(devices[device_name], VoxelDevice):
                    raise TypeError(f"Device {device_name} of assembly {unit_name} is not a VoxelDevice.")
                if device_name in stage_axes:
                    raise ValueError(
                        f"Device {device_name} of assembly {unit_name} is a stage axis and cannot be in an assembly."
                    )

    def get_channel_builder(self) -> "ChannelBuilder":
        """Get a channel builder for the instrument."""
        return ChannelBuilder(self)

    def add_channel(self, channel: "ImagingChannel") -> None:
        """Add a channel to the instrument."""
        if channel.name in self.channels:
            if self.channels[channel.name] is channel:
                return
            self.log.warning(f"Channel {channel.name} already exists. Overwriting.")
        self.channels[channel.name] = channel
