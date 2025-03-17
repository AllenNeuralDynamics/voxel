"""Voxel Compatible Devices."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import IntEnum, StrEnum
from functools import cached_property
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from voxel.utils.descriptors.deliminated import (
    DeliminatedInt,
    DeliminatedFloat,
    DeliminatedProperty,
)
from voxel.utils.descriptors.enumerated import EnumeratedProperty, EnumeratedValue
from voxel.utils.log_config import get_component_logger
from voxel.utils.vec import Vec2D, Vec3D

if TYPE_CHECKING:
    from voxel.daq.tasks.wavegen import WaveGenChannel

type VoxelPropertyType = Literal[
    "deliminated", "enumerated", "string", "number", "boolean", "vector", "dict"
]


class VoxelPropertyModel[T: int | float](BaseModel):
    name: str
    type: str  # VoxelPropertyType
    value: str | int | float | Vec2D[T] | Vec3D[T] | object
    min: int | float | None = None
    max: int | float | None = None
    step: int | float | None = None
    write: bool = True
    options: (
        Sequence[str]
        | Sequence[int]
        | Sequence[float]
        | Sequence[int | float | str]
        | None
    ) = None


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
    """Base class for all exceptions raised by devices."""

    pass


class VoxelDeviceConnectionError(VoxelDeviceError):
    """Custom exception for camera discovery errors."""

    pass


class VoxelPropertyDetails(BaseModel):
    label: str | None = None
    unit: str | None = None
    description: str | None = None


class VoxelDeviceModel(BaseModel):
    name: str
    type: VoxelDeviceType
    properties: dict[str, "VoxelPropertyModel"]


class VoxelSignalModel(BaseModel):
    name: str
    value: int | float | str | bool | Vec2D | Vec3D


def merge_dicts(dict1: dict, dict2: dict) -> dict:
    """Recursively merge two dictionaries. Merge: lists, sets. Overwrite other types.
    :param dict1: base dictionary
    :param dict2: dictionary to merge
    :return: merged dictionary. updated dict1
    :type dict1: dict
    :type dict2: dict
    :rtype: dict
    """
    for key, value in dict2.items():
        if key in dict1 and isinstance(value, dict) and isinstance(dict1[key], dict):
            merge_dicts(dict1[key], value)
        elif key in dict1 and isinstance(value, set) and isinstance(dict1[key], set):
            dict1[key] = dict1[key].union(value)
        elif key in dict1 and isinstance(value, list) and isinstance(dict1[key], list):
            dict1[key] += value
        else:
            dict1[key] = value
    return dict1


class VoxelDevice(ABC):
    """Base class for all voxel devices."""

    _details: dict[str, VoxelPropertyDetails] = {}
    _signals: set[str] = set()

    def __init__(self, name: str, device_type: VoxelDeviceType):
        """Initialize the device.
        :param name: The unique identifier of the device.
        :type name: str
        """
        self.name = name
        self.log = get_component_logger(self)
        self.acq_daq_channel: WaveGenChannel
        self.device_type: VoxelDeviceType = device_type

    def __init_subclass__(cls) -> None:
        """Recursively merge some attributes from all base classes."""

        for parent_class in cls.mro()[1:-1]:
            if hasattr(parent_class, "details"):
                cls._details = merge_dicts(cls._details, parent_class.details)

    def apply_settings(self, settings: dict):
        """Apply settings to the device."""
        for key, value in settings.items():
            try:
                setattr(self, key, value)
            except AttributeError:
                self.log.error(f"Instance '{self.name}' has no attribute '{key}'")
            except Exception as e:
                self.log.error(f"Error setting '{key}' for '{self.name}': {str(e)}")
                raise
        self.log.info(f"Applied settings to '{self.name}'")

    @abstractmethod
    def close(self):
        """Close the device."""
        pass

    def __str__(self):
        return f"{self.__class__.__name__}[{self.name}]"

    @cached_property
    def properties(self) -> dict[str, Any]:
        ignore_list = {
            "name",
            "device_type",
            "log",
            "property_names",
            "acq_daq_channel",
        }
        return {
            k: v
            for k, v in {**vars(type(self)), **vars(self)}.items()
            if not callable(v) and not k.startswith("_") and k not in ignore_list
        }

    @cached_property
    def property_names(self) -> set[str]:
        return set(self.properties.keys())

    def get_property(self, prop_name: str) -> VoxelPropertyModel | None:
        """Get a snapshot of the device's current state."""

        def get_property_type(prop_value: Any) -> str:
            if isinstance(prop_value, (DeliminatedFloat | DeliminatedInt)):
                return "deliminated"
            if isinstance(prop_value, (EnumeratedValue, IntEnum, StrEnum)):
                return "enumerated"
            if hasattr(prop_value, "__dataclass_fields__") or hasattr(
                prop_value, "__fields__"
            ):
                return "dict"
            else:
                return type(prop_value).__name__.lower()

        prop_obj = self.properties[prop_name]
        prop_value = getattr(self, prop_name)
        prop_type = get_property_type(prop_value)

        min_value = None
        max_value = None
        step = None
        options = None
        write = False

        if isinstance(prop_obj, DeliminatedProperty):
            min_value = prop_value.min_value
            max_value = prop_value.max_value
            step = prop_value.step
        elif isinstance(prop_obj, EnumeratedProperty):
            options = prop_value.options
        elif isinstance(prop_value, (IntEnum, StrEnum)):
            options = [member.value for member in prop_value.__class__]

        if isinstance(prop_obj, (property, DeliminatedProperty, EnumeratedProperty)):
            write = prop_obj.fset is not None

        if prop_type not in {
            "deliminated",
            "enumerated",
            "int",
            "float",
            "dict",
            "str",
            "bool",
            "vec2d",
            "vec3d",
        }:
            prop_value = str(prop_value)

        return VoxelPropertyModel(
            name=prop_name,
            type=prop_type,
            value=prop_value,
            min=min_value,
            max=max_value,
            step=step,
            options=options,
            write=write,
        )

    def get_properties(
        self, prop_names: set[str] | None = None
    ) -> dict[str, VoxelPropertyModel]:
        """Get a snapshot of the device's current state."""
        prop_names = (
            {name for name in prop_names if name in self.property_names}
            if prop_names
            else self.property_names
        )

        props: dict[str, VoxelPropertyModel] = {}
        for prop_name in prop_names:
            if model := self.get_property(prop_name):
                props[prop_name] = model
        return props

    @property
    def snapshot(self) -> "VoxelDeviceModel":
        return VoxelDeviceModel(
            name=self.name,
            type=self.device_type,
            properties=self.get_properties(),
        )

    def get_signals(self) -> dict[str, VoxelSignalModel]:
        """Get a snapshot of the device's current state."""
        signals = {}
        for signal_name in self._signals:
            signal_value = getattr(self, signal_name)
            if isinstance(signal_value, (int | float | str | bool | Vec2D | Vec3D)):
                signals[signal_name] = VoxelSignalModel(
                    name=signal_name, value=signal_value
                )
            else:
                self.log.error(
                    f"Signal '{signal_name}' has an unsupported type: {type(signal_value)}"
                )
        return signals
