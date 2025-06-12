from pathlib import Path
from typing import Self

from voxel.devices.base import VoxelDevice
from voxel.devices.interfaces import VoxelCamera, VoxelFilterWheel, VoxelLaser, VoxelLinearAxis, VoxelRotationAxis
from voxel.pipeline.io.manager import IOManager
from voxel.pipeline.local_pipeline import ImagingPipeline
from voxel.pipeline.preview.publisher import PreviewManager
from voxel.utils.build import build_object_group
from voxel.utils.log_config import get_component_logger

from .optical_paths.channel import Channel
from .optical_paths.detection import DetectionPath
from .optical_paths.illumination import IlluminationPath
from .imaging_unit import ImagingUnit
from .schemas import ChannelDefinition, ImagingUnitDefinition, InstrumentConfig, InstrumentLayout, InstrumentMetadata
from .specimen_stage import SpecimenStage


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
        self._preview_manager = PreviewManager()

        self._stage = self._create_stage()
        self._detection: dict[str, DetectionPath] = self._create_detection_units()
        self._illumination: dict[str, IlluminationPath] = self._create_illumination_units()

        self._channels: dict[str, Channel] = {}
        for definition in channel_definitions:
            self.add_channel(definition)

        self._imaging_units: dict[str, ImagingUnitDefinition] = {}

        self._current_unit: ImagingUnit | None = None

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
    def preview_manager(self) -> PreviewManager:
        return self._preview_manager

    @property
    def detection(self) -> dict[str, DetectionPath]:
        return self._detection

    @property
    def illumination(self) -> dict[str, IlluminationPath]:
        return self._illumination

    @property
    def channels(self) -> dict[str, Channel]:
        """Get all channels in the instrument.
        :return: A dictionary of channels, keyed by channel name.
        :rtype: dict[str, Channel]
        """
        return self._channels

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

    def add_imaging_unit_definition(self, definition: ImagingUnitDefinition) -> None:
        """Add an imaging unit definition to the instrument. Validates the channels and settings.
        :param definition: The imaging unit definition.
        :type definition: ImagingUnitDefinition
        """
        if definition.name in self._imaging_units:
            self.log.warning(f"Imaging unit '{definition.name}' already exists, will be overwritten.")
        try:
            ImagingUnit(definition=definition, instrument=self)
            # no errors means the imaging unit is valid
            self._imaging_units[definition.name] = definition
        except ValueError as e:
            self.log.error(f"Failed to resolve channels for imaging unit '{definition.name}': {e}")
            return

    @property
    def active_unit(self) -> "ImagingUnit | None":
        """Get the currently active imaging unit."""
        return self._current_unit

    def set_active_unit(self, unit: "ImagingUnit") -> None:
        """Set the current imaging unit."""
        if self._current_unit is not None:
            raise RuntimeError(f"Cannot set active unit to '{unit.name}' because another unit is already active.")
        self._current_unit = unit
        self.log.info(f"Active imaging unit set to '{unit.name}'.")

    def reset_active_unit(self) -> None:
        """Reset the current imaging unit."""
        self._current_unit = None

    def _create_detection_units(self) -> dict[str, DetectionPath]:
        """Create the detection units for the instrument."""
        detection_units = {}
        for name, model in self._layout.detection.items():
            if model.pipeline.is_local:
                pipeline = ImagingPipeline(
                    camera=self.cameras[name], io_manager=self.io_manager, preview_pub=self.preview_manager
                )
            else:
                raise NotImplementedError(f"Remote pipelines are not implemented yet for camera {name}")
            detection_units[name] = DetectionPath(
                pipeline=pipeline,
                filter_wheels=[self.filter_wheels[fw_name] for fw_name in model.filter_wheels],
                aux_devices=[self.devices[device_name] for device_name in model.aux_devices],
            )
        return detection_units

    def _create_illumination_units(self) -> dict[str, IlluminationPath]:
        """Create the illumination units for the instrument."""
        illumination_units = {}
        for name, model in self._layout.illumination.items():
            illumination_units[name] = IlluminationPath(
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
