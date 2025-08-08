from .base import VoxelDevice
from .z_settings import ZPoint, ZSetting, ZSettingsCollection


class ConfiguredDevice[T: VoxelDevice]:
    """A class representing a device with a configuration."""

    def __init__(self, device: T, z_settings: ZSettingsCollection | None = None) -> None:
        self._device = device
        self._log = device._log
        self._z_settings: ZSettingsCollection = {}
        if z_settings:
            for prop_name, setting in z_settings.items():
                self._add_setting_entry(prop_name, setting, skip_invalid=True)

    @property
    def instance(self) -> T:
        """Allows ConfiguredDevice to be used as a descriptor."""
        return self._device

    @property
    def name(self) -> str:
        return self.instance.uid

    @property
    def z_settings(self) -> ZSettingsCollection:
        return self._z_settings

    def save_current_value(self, prop_name: str, z_pos: float) -> None:
        """
        Saves the value for a property at the current z position.
        If the property does not exist, it will be created with a single ZPoint.
        """
        if value := getattr(self.instance, prop_name, None):
            self.add_setting_point(prop_name, ZPoint(z=z_pos, value=value))
            self._log.debug(f"Saved value '{value}' for property '{prop_name}' at z={z_pos}.")

    def add_setting_point(self, prop_name: str, point: ZPoint) -> None:
        """Adds a ZPoint. Creates ZSetting if prop_name is new and valid."""
        if prop_name not in self._z_settings:
            new_z_setting = ZSetting([point])
            self._add_setting_entry(prop_name, new_z_setting)
        else:
            self._z_settings[prop_name].add_point(point)

    async def apply_settings(self, current_z: float | None = None) -> None:
        if not self._z_settings:
            return

        for prop_name, z_setting in self._z_settings.items():
            value_to_set = z_setting.get_value(current_z)
            try:
                setattr(self.instance, prop_name, value_to_set)
                self._log.debug(f"Set attribute/property '{self.name}.{prop_name}' = {value_to_set}")
            except Exception as e:  # Catch errors from the device's actual setter
                self._log.error(f"Failed to apply setting: '{self.name}.{prop_name}' = '{value_to_set}': {e}")

    def _validate_device_setting(self, prop_name: str, setting: ZSetting) -> bool:
        """
        Validates a single setting against the device's properties.
        Raises an error if the setting is invalid.
        :param prop_name: The name of the property to validate.
        :param setting: The ZSetting to validate.
        :raises ValueError: If the setting is invalid.
        """
        if not hasattr(self.instance, prop_name):
            self._log.warning(f"Property '{prop_name}' does not exist in device '{self.instance.uid}'.")
            return False
        prop_metadata = self.instance.get_property_details(prop_name)
        if not prop_metadata:
            prop_descriptor = getattr(type(self.instance), prop_name)
            if prop_descriptor:
                if prop_descriptor.fset is not None:
                    return True  # Property exists but has no metadata, assume it's writable
                else:
                    self._log.warning(f"Property '{prop_name}' is read-only in device '{self.instance.uid}'.")
                    return False
            else:
                self._log.warning(f"Property '{prop_name}' is not defined in device '{self.instance.uid}'.")
                return False
        else:
            return not prop_metadata.read_only

    def _add_setting_entry(self, prop_name: str, setting: ZSetting, skip_invalid: bool = False) -> None:
        """
        Validates a setting and adds it to the device's settings.
        Raises an error if the setting is invalid.
        :param prop_name: The name of the property to validate.
        :param setting: The ZSetting to validate and add.
        """
        if not self._validate_device_setting(prop_name, setting):
            if skip_invalid:
                self._log.warning(f"Skipping invalid setting '{prop_name}' for device '{self.instance.uid}'.")
                return
            raise ValueError(f"Invalid setting '{prop_name}' for device '{self.instance.uid}'.")
        self._z_settings[prop_name] = setting
