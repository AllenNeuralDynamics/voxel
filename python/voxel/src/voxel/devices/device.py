"""Voxel Compatible Devices."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel

from voxel.devices.descriptions import AttrDescription, WithDescriptions, describe
from voxel.utils.log import VoxelLogging
from voxel.utils.vec import Vec2D, Vec3D

if TYPE_CHECKING:
    from voxel.daq.acq_task import WaveGenChannel


class VoxelDeviceType(StrEnum):
    HUB = 'hub'
    CAMERA = 'camera'
    LENS = 'lens'
    LASER = 'laser'
    FILTER = 'filter'
    FILTER_WHEEL = 'filter_wheel'
    LINEAR_AXIS = 'linear_axis'
    ROTATION_AXIS = 'rotation_axis'
    FLIP_MOUNT = 'flip_mount'
    TUNABLE_LENS = 'tunable_lens'
    POWER_METER = 'power_meter'
    AOTF = 'aotf'
    CHILLER = 'chiller'


class VoxelDeviceError(Exception):
    pass


class VoxelDeviceConnectionError(VoxelDeviceError):
    pass


class VoxelPropertyValue(BaseModel):
    name: str  # Corresponds to VoxelPropertySchema.name
    value: int | float | bool | str | Vec2D | Vec3D

    # Dynamic constraints
    min: int | float | None = None  # Minimum value for numeric types
    max: int | float | None = None  # Maximum value for numeric types
    step: int | float | None = None  # Step size for numeric types
    options: Sequence[str | int | float] | None = None  # Valid options for enumerated types
    is_enabled: bool = True  # Whether the property is enabled or not

    error_message: str | None = None  # Error message if the property is invalid


class VoxelDevice(ABC, WithDescriptions):
    """Base class for all voxel devices."""

    def __init__(self, uid: str, device_type: VoxelDeviceType) -> None:
        """Initialize the device.

        Args:
            uid: The unique identifier of the device.
            device_type: The type of the device.

        """
        self._uid = uid
        self.log = VoxelLogging.get_logger(obj=self)
        self._acq_daq_channel: WaveGenChannel
        self._device_type: VoxelDeviceType = device_type

    @property
    @describe(label='Device Name', description='The unique identifier of the device.')
    def uid(self) -> str:
        """A unique identifier of the device."""
        return self._uid

    @property
    @describe(label='Device Type', description='The type of the device.')
    def device_type(self) -> VoxelDeviceType:
        """The type of the device."""
        return self._device_type

    def get_property_description(self, prop_name: str) -> AttrDescription | None:
        """Get the details of a property by its name."""
        return self.VOXEL_DESCRIPTIONS.get(prop_name)

    def get_property(self, prop_name: str) -> VoxelPropertyValue | None:
        """Get the value of a property by its name.

        Args:
            prop_name : The name of the property.

        Returns:
            VoxelPropertyValue | None: The value of the property, or None if the property does not exist.
        """
        prop_value = getattr(self, prop_name, None)
        if prop_value is None:
            self.log.warning("Property '%s' is not set in device '%s'.", prop_name, self.uid)
            if prop_name in self.VOXEL_DESCRIPTIONS:
                self.log.warning("Property '%s' is listed in the device schema, but has no value.", prop_name)
            return None

        prop_metadata = self.get_property_description(prop_name)
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
    def close(self) -> None:
        """Close the device."""

    def snapshot(self) -> dict[str, VoxelPropertyValue]:
        """Get a snapshot of the device's current state.

        Returns:
             A dictionary of property names and their current values.
        """
        props: dict[str, VoxelPropertyValue] = {}
        for prop_name in self.VOXEL_DESCRIPTIONS:
            if model := self.get_property(prop_name):
                props[prop_name] = model
        return props

    def __str__(self) -> str:
        return f'{self.__class__.__name__}[{self.uid}]'


if __name__ == '__main__':
    from rich import print

    class ExampleDevice(VoxelDevice):
        def close(self) -> None:
            print(f'Closing device {self.uid}')

        @property
        @describe(label='Example Property', description='An example property.')
        def example_property(self) -> int:
            return 42

    device = ExampleDevice(uid='example_device_1', device_type=VoxelDeviceType.CAMERA)
    print(f'Device UID: {device.uid}')
    print(f'Device Type: {device.device_type}')
    prop = device.get_property('example_property')
    if prop:
        print('Property `example_property`:', prop.model_dump())
    else:
        print('Property `example_property` not found.')
    device.close()
