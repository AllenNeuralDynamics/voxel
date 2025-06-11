"""Voxel Compatible Devices."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel

from voxel.utils.descriptors.deliminated import DeliminatedProperty
from voxel.utils.descriptors.enumerated import EnumeratedStrProperty
from voxel.utils.log_config import get_component_logger
from voxel.utils.vec import Vec2D, Vec3D

if TYPE_CHECKING:
    from voxel.daq.tasks.wavegen import WaveGenChannel


class VoxelDeviceType(StrEnum):
    HUB = "hub"
    CAMERA = "camera"
    LENS = "lens"
    LASER = "laser"
    FILTER = "filter"
    FILTER_WHEEL = "filter_wheel"
    LINEAR_AXIS = "linear_axis"
    ROTATION_AXIS = "rotation_axis"
    FLIP_MOUNT = "flip_mount"
    TUNABLE_LENS = "tunable_lens"
    POWER_METER = "power_meter"
    AOTF = "aotf"
    CHILLER = "chiller"


class VoxelDeviceError(Exception):
    pass


class VoxelDeviceConnectionError(VoxelDeviceError):
    pass


class VoxelPropertyValue[T: int | float | bool | str | Vec2D | Vec3D](BaseModel):
    name: str  # Corresponds to VoxelPropertySchema.name
    value: T

    # Dynamic constraints
    min: int | float | None = None  # Minimum value for numeric types
    max: int | float | None = None  # Maximum value for numeric types
    step: int | float | None = None  # Step size for numeric types
    options: Sequence[str | int | float] | None = None  # Valid options for enumerated types
    is_enabled: bool = True  # Whether the property is enabled or not

    error_message: str | None = None  # Error message if the property is invalid


class VoxelPropertyDetails(BaseModel):
    label: str | None = None
    unit: str | None = None
    description: str | None = None
    read_only: bool = True

    def merge_higher(self, higher: Self) -> None:
        """Merge another VoxelPropertyDetails instance into this one."""
        self.label = higher.label if higher.label is not None else self.label
        self.unit = higher.unit if higher.unit is not None else self.unit
        self.description = higher.description if higher.description is not None else self.description
        self.read_only = higher.read_only


def generate_ui_label(attr_name: str) -> str:
    """Generate a user-friendly label for a property name."""
    return attr_name.replace("_", " ").capitalize()


def property_metadata(label: str | None = None, unit: str | None = None, description: str | None = None):
    def decorator(fget: Callable[[Any], Any]):
        metadata = VoxelPropertyDetails(
            label=label if label is not None else generate_ui_label(fget.__name__),
            description=description if description is not None else fget.__doc__,
            unit=unit,
        )

        fget.__setattr__("_voxel_property_metadata", metadata)
        return fget

    return decorator


class VoxelDevice(ABC):
    """Base class for all voxel devices."""

    _voxel_property_metadata: dict[str, VoxelPropertyDetails] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        parent_registry_to_copy = {}
        for parent in cls.mro()[1:]:
            if hasattr(parent, "_voxel_property_metadata"):
                parent_reg_attr = getattr(parent, "_voxel_property_metadata")
                if isinstance(parent_reg_attr, dict):
                    parent_registry_to_copy = {
                        k: v.model_copy(deep=True) if isinstance(v, VoxelPropertyDetails) else v
                        for k, v in parent_reg_attr.items()
                    }
                break  # Found the first parent in MRO with the registry

        # 2. Add/override with details defined directly in 'cls' (e.g., from decorators or docstrings)
        for attr_name, attr_value in vars(cls).items():
            if attr_name.startswith("_"):
                continue
            if not isinstance(attr_value, (property, DeliminatedProperty, EnumeratedStrProperty)):
                continue
            fget = attr_value.fget
            if not fget:
                continue
            metadata: VoxelPropertyDetails | None = getattr(fget, "_voxel_property_metadata")
            if not metadata:
                # set a new details attribute if it does not exist
                metadata = VoxelPropertyDetails(
                    label=generate_ui_label(attr_name),
                    description=fget.__doc__,
                )
            metadata.read_only = attr_value.fset is None

            if attr_name in parent_registry_to_copy:
                parent_registry_to_copy[attr_name].merge_higher(higher=metadata)
            else:
                parent_registry_to_copy[attr_name] = metadata

        cls._voxel_property_metadata = parent_registry_to_copy

    def __init__(self, name: str, device_type: VoxelDeviceType):
        """Initialize the device.
        :param name: The unique identifier of the device.
        :type name: str
        """
        self._name = name
        self._log = get_component_logger(self)
        self._acq_daq_channel: WaveGenChannel
        self._device_type: VoxelDeviceType = device_type

    @property
    @property_metadata(label="Device Name", description="The unique identifier of the device.")
    def name(self) -> str:
        """A unique identifier of the device."""
        return self._name

    @property
    @property_metadata(label="Device Type", description="The type of the device.")
    def device_type(self) -> VoxelDeviceType:
        """The type of the device."""
        return self._device_type

    def get_property_details(self, prop_name: str) -> VoxelPropertyDetails | None:
        """Get the details of a property by its name."""
        return self._voxel_property_metadata.get(prop_name)

    def get_property(self, prop_name: str) -> VoxelPropertyValue | None:
        """Get the value of a property by its name.
        :param prop_name: The name of the property.
        :type prop_name: str
        :return: The value of the property, or None if the property does not exist.
        :rtype: VoxelPropertyValue | None
        """
        prop_value = getattr(self, prop_name, None)
        if prop_value is None:
            self._log.warning(f"Property '{prop_name}' is not set in device '{self.name}'.")
            if prop_name in self._voxel_property_metadata:
                self._log.warning(f"Property '{prop_name}' is listed in the device schema, but has no value.")
            return None

        prop_metadata = self.get_property_details(prop_name)
        is_enabled = not prop_metadata.read_only if prop_metadata else True

        try:
            min_value = prop_value.min_value
        except AttributeError:
            min_value = None
        try:
            max_value = prop_value.max_value
        except AttributeError:
            max_value = None
        try:
            step = prop_value.step
        except AttributeError:
            step = None
        try:
            options = prop_value.options
        except AttributeError:
            options = None

        return VoxelPropertyValue(
            name=prop_name,
            value=prop_value,
            min=min_value,
            max=max_value,
            step=step,
            options=options,
            is_enabled=is_enabled,
        )

    @abstractmethod
    def close(self):
        """Close the device."""
        pass

    def snapshot(self) -> dict[str, VoxelPropertyValue]:
        """Get a snapshot of the device's current state.
        :return: A dictionary of property names and their values.
        :rtype: dict[str, VoxelPropertyValue]
        """
        props: dict[str, VoxelPropertyValue] = {}
        for prop_name in self._voxel_property_metadata:
            if model := self.get_property(prop_name):
                props[prop_name] = model
        return props

    def __str__(self):
        return f"{self.__class__.__name__}[{self.name}]"
