import bisect
from functools import total_ordering
from logging import Logger
from typing import Any, Self

import numpy as np
from pydantic import BaseModel, model_validator

from voxel.devices.base import VoxelDevice
from voxel.devices.camera import VoxelCameraProxy
from voxel.utils.descriptors.deliminated import DeliminatedProperty
from voxel.utils.descriptors.enumerated import EnumeratedProperty


@total_ordering
class ZPoint[T](BaseModel):
    z: float
    value: T
    model_config = {"frozen": True}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ZPoint):
            return NotImplemented
        return (self.z, self.value) == (other.z, other.value)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ZPoint):
            return NotImplemented
        if self.z == other.z:
            return False
        return self.z < other.z


class ZSetting[T](BaseModel):
    points: list[ZPoint[T]]

    @model_validator(mode="after")
    def check_and_sort_points(self) -> Self:
        if not self.points:
            raise ValueError("ZSetting points cannot be empty")
        self.points.sort()
        return self

    def __setitem__(self, z: float, value: T) -> None:
        self.add_point(ZPoint(z=z, value=value))

    def __getitem__(self, z: float) -> T:
        return self.get_value(z)

    def __delitem__(self, z: float) -> None:
        self.remove_point(z)

    @property
    def z_coords(self) -> list[float]:
        return [p.z for p in self.points]

    # TODO: Use pydantic's type system to infer the type of the generic
    @property
    def value_type(self) -> type[T]:
        return type(self.points[0].value)

    @property
    def is_numeric(self) -> bool:
        return isinstance(self.points[0].value, (int, float, np.number))

    def add_point(self, point: ZPoint[T]) -> None:
        if self.is_numeric and not isinstance(point.value, (int, float, np.number)):
            raise TypeError(f"Numeric ZSetting values must be numeric. Got {type(point.value)}.")
        if not self.is_numeric and not isinstance(point.value, self.value_type):
            raise TypeError(f"ZSetting values must be of type {self.value_type}. Got {type(point.value)}.")

        for i, p in enumerate(self.points):
            if p.z == point.z:
                self.points[i] = point
                return
        bisect.insort_left(self.points, point)

    def merge(self, other: Self) -> None:
        """
        Merges another ZSetting into this one.
        Points from the other setting are added to this one.
        If a point with the same z-coordinate exists, it is replaced.
        """
        if not isinstance(other, ZSetting) or self.value_type != other.value_type:
            raise TypeError("Can only merge with another ZSetting of similar type.")
        for point in other.points:
            self.add_point(point)

    def get_value(self, z: float | None = None) -> T:
        """
        Retrieves the value at a given z-coordinate.
        - If z is None, it returns the value of the point with the median z-coordinate.
          (Or, if values are non-numeric, the value of the middle point by index).
        - If only one point exists, its value is returned.
        - If an exact z-match exists, that point's value is returned.
        - For numeric values, interpolates if no exact match.
        - For non-numeric values, returns the value of the nearest point with z_point <= z.
          If no such point, returns the value of the first point (smallest z).
        """
        if not self.points:
            raise ValueError("ZSetting has no points from which to get a value.")

        # if only one point is present, return its value
        if len(self.points) == 1:
            return self.points[0].value

        # if z is not provided, set it to the middle point
        z = z if z is not None else self.points[len(self.points) // 2].z

        # if an exact match is found, return the value
        for point in self.points:
            if point.z == z:
                return point.value

        # At this point, we know z is not None and not an exact match.
        try:
            # Attempt to create a numeric array for setting_vals.
            # This will raise ValueError/TypeError if values are not numeric-like.
            setting_vals_np = np.array([p.value for p in self.points], dtype=float)
            return np.interp(z, self.z_coords, setting_vals_np).item()
        except (ValueError, TypeError):
            if self.is_numeric:
                print(f"Warning: Numeric interpolation failed for z={z}. Using nearest floor logic.")
            for p in reversed(self.points):
                if p.z <= z:
                    return p.value
            return self.points[0].value

    def remove_point(self, z: float) -> None:
        """
        Removes a point with the specified z-coordinate unless it is the only point.
        Raises IndexError if the point is the only one in the list.
        Raises ValueError if no such point exists.
        """
        if len(self.points) == 1:
            raise IndexError("Cannot remove the only point in the ZSetting.")
        for i, p in enumerate(self.points):
            if p.z == z:
                del self.points[i]
                return
        raise ValueError(f"No point found with z-coordinate {z}.")


type SettingsBlock = dict[str, ZSetting[Any]]  # prop_name -> ZSetting for that property


class ConfiguredDevice[T: VoxelDevice | VoxelCameraProxy]:
    """
    A class representing a device with a configuration.
    The configuration is a dictionary containing ZSettings.
    """

    _settings: SettingsBlock

    def __init__(self, device: T, settings: SettingsBlock | None = None) -> None:
        self.device = device
        self._settings = {}
        if settings:
            for prop_name, setting in settings.items():
                self._validate_and_add_setting_entry(prop_name, setting)

    @property
    def name(self) -> str:
        return self.device.name

    @property
    def log(self) -> Logger:
        return self.device.log

    @property
    def settings(self) -> SettingsBlock:
        return self._settings

    def add_setting_point(self, prop_name: str, point: ZPoint[Any]) -> None:
        """Adds a ZPoint. Creates ZSetting if prop_name is new and valid."""
        if prop_name not in self._settings:
            new_z_setting = ZSetting(points=[point])  # ZSetting validates point type consistency internally
            self._validate_and_add_setting_entry(prop_name, new_z_setting)
        else:
            self._settings[prop_name].add_point(point)

    def merge(self, other: Self) -> None:
        """
        Merges settings from another ConfiguredDevice with the same device instance into this one.
        If a setting already exists, points will be combined with the new ones taking precedence in case of collisions.
        - Useful for creating imagingGroups with channels that share devices.
        """
        if self.device is not other.device:
            raise ValueError("Cannot merge settings for different device instances.")

        for prop_name, other_z_setting in other._settings.items():
            if prop_name in self._settings:
                try:
                    self._settings[prop_name].merge(other_z_setting)
                except TypeError as e:
                    self.log.warning(f"Could not merge ZSetting for '{prop_name}' due to type issue: {e}")
            else:
                # If new, validate and add
                self._validate_and_add_setting_entry(prop_name, other_z_setting)

    def apply_settings(self, current_z: float | None = None) -> None:
        if not self._settings:
            return

        for prop_name, z_setting in self._settings.items():
            value_to_set = z_setting.get_value(current_z)
            setter_method_name = self._get_set_method_name(prop_name)
            # At this point, prop_name is known to be settable and type-compatible
            # due to checks in _validate_and_add_setting_entry.
            try:
                if hasattr(self.device, setter_method_name) and callable(getattr(self.device, setter_method_name)):
                    getattr(self.device, setter_method_name)(value_to_set)
                    self.log.debug(f"Called method '{self.name}.{setter_method_name}({value_to_set})'")
                else:
                    setattr(self.device, prop_name, value_to_set)
                    self.log.debug(f"Set attribute/property '{self.name}.{prop_name}' = {value_to_set}")
            except Exception as e:  # Catch errors from the device's actual setter
                self.log.error(
                    f"Error during device set operation for '{self.name}.{prop_name}' "
                    f"with value '{value_to_set}': {e}"
                )

    def get_setting(self, prop_name: str) -> ZSetting[Any] | None:
        """
        Returns the ZSetting for the given property name.
        If the property name is not found, returns None.
        """
        return self._settings.get(prop_name, None)

    # TODO: improve this to check type compatibility more robustly
    def _validate_and_add_setting_entry(self, prop_name: str, setting: ZSetting[Any]) -> None:
        if prop_name in self._settings:
            return

        if not hasattr(self.device, prop_name):
            self.log.warning(f"Attempting to configure a non-existent property. Prop_name: {prop_name}")
            return

        if not self._is_property_settable(prop_name):
            self.device.log.warning(f"Attempting to configure a non-settable property. Prop_name: {prop_name}")
            return

        device_prop = getattr(self.device, prop_name)
        exact_match = isinstance(device_prop, setting.value_type)
        both_are_numeric = self._is_property_numeric(prop_name) and setting.is_numeric
        if exact_match or both_are_numeric:
            self._settings[prop_name] = setting
        else:
            self.log.warning(f"Type mismatch for {prop_name}: {type(device_prop)} vs {setting.value_type}")

    def _is_property_numeric(self, prop_name: str) -> bool:
        class_attr = getattr(type(self.device), prop_name, None)
        if class_attr is None or not isinstance(class_attr, type):
            return False
        return issubclass(class_attr, (int, float, np.number))

    def _get_set_method_name(self, setting_name: str) -> str:
        return f"set_{setting_name}"

    def _is_property_settable(self, prop_name: str) -> bool:
        if prop_name.startswith("_") or not hasattr(self.device, prop_name):
            return False

        prop = getattr(type(self.device), prop_name, None)

        if hasattr(prop, "__set__"):
            return True

        # More robust check for properties with setters
        if isinstance(prop, (property, DeliminatedProperty, EnumeratedProperty)):
            return prop.fset is not None

        return not callable(getattr(self.device, prop_name))
