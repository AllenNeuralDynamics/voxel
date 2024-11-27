from typing import Any


class SettingsManager:
    def __init__(self, channels: dict[str, Any], devices: dict[str, Any]):
        """
        Initialize the SettingsManager with references to channels and devices.
        :param channels: A dictionary of channel objects (keyed by channel name).
        :param devices: A dictionary of device objects (keyed by device name).
        """
        self.channels = channels
        self.devices = devices

    def apply_settings(self, settings: dict) -> None:
        """
        Apply the provided settings to the appropriate channels or devices, ensuring specific settings take precedence.
        :param settings: A dictionary of settings patterns and values.
        """
        # Separate general and specific settings
        general_settings = {k: v for k, v in settings.items() if k.endswith(".*")}
        specific_settings = {k: v for k, v in settings.items() if not k.endswith(".*")}

        # Apply general settings first
        self._apply_settings(general_settings)

        # Apply specific settings to override
        self._apply_settings(specific_settings)

    def _apply_settings(self, settings: dict) -> None:
        """
        Apply the provided settings to the appropriate channels or devices.
        :param settings: A dictionary of settings patterns and values.
        """
        for pattern, value in settings.items():
            if pattern.startswith("channels."):
                # print(f"Applying settings to channels: {pattern} -> {value}")
                self._apply_channels_settings(pattern, value)
            elif pattern.startswith("devices."):
                # print(f"Applying settings to devices: {pattern} -> {value}")
                self._apply_device_settings(pattern, value)

    def _apply_device_settings(self, pattern: str, settings: Any) -> None:
        """
        Apply settings to a specific device.
        :param pattern: The pattern for devices (e.g., "devices.camera1").
        :param settings: The settings dictionary to apply.
        """
        for device_name, device in self.devices.items():
            if self._key_matches(pattern, f"devices.{device_name}"):
                device.apply_settings(settings)

    def _apply_channels_settings(self, pattern: str, settings: Any) -> None:
        """
        Apply settings to a channel's devices.
        :param pattern: The pattern for channels (e.g., "channels.channel1", "channels.channel1.laser").
        :param settings: The settings dictionary or value to apply.
        """

        def _apply_channel_device_settings(channel, device_type, device_settings):
            device = getattr(channel, device_type, None)
            if device:
                device.apply_settings(device_settings)
            else:
                raise AttributeError(f"Channel {channel.name} has no device of type '{device_type}'")

        valid_devices = {"camera", "laser", "filter"}
        for channel_name, channel in self.channels.items():
            if self._key_matches(pattern, f"channels.{channel_name}"):
                device_type = pattern.replace(f"channels.{channel_name}", "").split(".")[1]
                device_types = valid_devices if device_type == "*" else valid_devices.intersection({device_type})

                if len(device_types) == 1:
                    _apply_channel_device_settings(channel, device_type, settings)
                elif len(device_types) > 1:
                    for device_type in device_types:
                        if device_settings := settings.get(device_type, None):
                            print(
                                f"Applying settings: channel '{channel_name}' device '{device_type}': {device_settings}"
                            )
                            _apply_channel_device_settings(channel, device_type, device_settings)

    def _key_matches(self, pattern: str, key: str) -> bool:
        """
        Check if a key matches a pattern with wildcard support.
        :param pattern: The pattern to match (e.g., "channels.*", "*.laser", "channels.channel1.*").
        :param key: The key to match against (e.g., "channels.channel1.camera").
        :return: True if the key matches the pattern, otherwise False.
        """
        if "*" not in pattern:
            return pattern.startswith(key)

        # Split the pattern and key into parts
        pattern_parts = pattern.split(".")
        key_parts = key.split(".")

        # Early exit if lengths differ and there is no wildcard to absorb extra segments
        # if len(pattern_parts) != len(key_parts) and "*" not in pattern_parts:
        #     return False
        # print(f"Pattern parts: {pattern_parts}")
        # print(f"Key parts: {key_parts}")

        for pattern_part, key_part in zip(pattern_parts, key_parts):
            if pattern_part == "*":
                continue  # Wildcard matches any part
            if pattern_part != key_part:
                return False  # Mismatch in non-wildcard part

        return True

    def __repr__(self) -> str:
        return f"SettingsManager(channels={list(self.channels.keys())}, devices={list(self.devices.keys())})"


class MockDevice:
    def __init__(self, name):
        self.name = name
        self.enabled = False

    def apply_settings(self, settings: dict):
        for key, value in settings.items():
            setattr(self, key, value)

    @property
    def settings(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def __repr__(self):
        return f"MockDevice({self.name}, {", ".join(self.settings)})"


class MockCamera(MockDevice):
    def __init__(self, name):
        super().__init__(name)
        self.roi_width_px = 1024
        self.roi_height_px = 1024
        self.pixel_type = "MONO8"


class MockFilter(MockDevice):
    def __init__(self, name):
        super().__init__(name)


class MockLaser(MockDevice):
    def __init__(self, name):
        super().__init__(name)
        self.power_mw = 0


class MockChannel:
    def __init__(self, name, camera: MockCamera, laser: MockLaser, filter_: MockFilter):
        self.name = name
        self.camera = camera
        self.laser = laser
        self.filter = filter_

    def __repr__(self):
        return f"MockChannel({self.name}, {self.camera}, {self.laser}, {self.filter})"


# Devices
camera1 = MockCamera("camera1")
laser1 = MockLaser("laser1")
filter1 = MockFilter("filter1")
camera2 = MockCamera("camera2")
laser2 = MockLaser("laser2")
filter2 = MockFilter("filter2")

# Channels
channel1 = MockChannel("channel1", camera1, laser1, filter1)
channel2 = MockChannel("channel2", camera2, laser2, filter2)

# Dictionaries
channels = {
    "channel1": channel1,
    "channel2": channel2,
}
devices = {
    "camera1": camera1,
    "camera2": camera2,
    "laser1": laser1,
    "laser2": laser2,
    "filter1": filter1,
    "filter2": filter2,
}

settings = {
    # "devices.camera1": {
    #     "roi_width_px": 512,
    #     "roi_height_px": 512,
    # },
    # "channels.channel1.laser": {
    #     "power_mw": 50,
    # },
    # "channels.channel1.camera": {
    #     "exposure_time_ms": 25,
    # },
    # "channels.channel2.*": {
    #     "enabled": True,
    # },
    "channels.*": {
        "laser": {
            "power_mw": 120,
        },
        "filter": {
            "enabled": True,
        },
    },
}


def validate_device_settings(settings: dict):
    """
    Validate that the settings have been applied correctly to channels and devices.
    :param settings: The original settings dictionary.
    """
    errors = []

    # Validate general settings for all channels
    general_settings = {k: v for k, v in settings.items() if k.endswith(".*")}
    specific_settings = {k: v for k, v in settings.items() if not k.endswith(".*")}

    # General settings validation
    for channel_name, channel in channels.items():
        for setting_key, setting_value in general_settings.get("channels.*", {}).items():
            device = getattr(channel, setting_key, None)
            if device:
                for key, value in setting_value.items():
                    if getattr(device, key, None) != value:
                        errors.append(
                            f"Channel '{channel_name}' device '{setting_key}' failed validation: "
                            f"Expected {key}={value}, got {getattr(device, key, None)}"
                        )

    # Specific settings validation
    for pattern, setting_value in specific_settings.items():
        if pattern.startswith("channels."):
            channel_key = pattern.split(".")[1]
            if len(pattern.split(".")) > 2:
                device_type = pattern.split(".")[2]
                device = getattr(channels[channel_key], device_type, None)
                for key, value in setting_value.items():
                    if getattr(device, key, None) != value:
                        errors.append(
                            f"Channel '{channel_key}' device '{device_type}' failed validation: "
                            f"Expected {key}={value}, got {getattr(device, key, None)}"
                        )
            else:
                channel_devices = channels[channel_key]
                for device_type, device_settings in setting_value.items():
                    device = getattr(channel_devices, device_type, None)
                    for key, value in device_settings.items():
                        if getattr(device, key, None) != value:
                            errors.append(
                                f"Channel '{channel_key}' device '{device_type}' failed validation: "
                                f"Expected {key}={value}, got {getattr(device, key, None)}"
                            )

        elif pattern.startswith("devices."):
            device_key = pattern.split(".")[1]
            device = devices.get(device_key)
            for key, value in setting_value.items():
                if getattr(device, key, None) != value:
                    errors.append(
                        f"Device '{device_key}' failed validation: "
                        f"Expected {key}={value}, got {getattr(device, key, None)}"
                    )

    if errors:
        print("Validation failed with errors:")
        for error in errors:
            print(f"- {error}")
    else:
        print("All settings validated successfully!")


if __name__ == "__main__":
    import json

    # Initialize the SettingsManager
    settings_manager = SettingsManager(channels, devices)

    # Apply settings dynamically
    settings_manager.apply_settings(settings)

    # Print updated objects
    # for channel in channels.values():
    #     print(json.dumps(channel.camera.settings, indent=2))
    #     print(json.dumps(channel.laser.settings, indent=2))
    #     print(json.dumps(channel.filter.settings, indent=2))

    for device in devices.values():
        print(json.dumps(device.settings, indent=2))

    # Validate the settings
    validate_device_settings(settings)

    # output:
    # {
    #   "roi_width_px": 512,
