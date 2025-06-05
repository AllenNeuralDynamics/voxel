from typing import Self

from voxel.channel import Channel
from voxel.devices import VoxelCamera, VoxelDevice, VoxelFilterWheel, VoxelLaser
from voxel.instrument import ChannelConfiguration, DetectionPathDefinition, IlluminationPathDefinition, Instrument
from voxel.settings import SettingsBlock, ZPoint, ZSetting


class ChannelBuilder:
    def __init__(self, instrument: Instrument):
        self.instrument = instrument
        self._reset_state()

    @property
    def detection_assemblies(self) -> dict[str, DetectionPathDefinition]:
        """Get the detection assemblies in the instrument."""
        return self.instrument.assembly.detection

    @property
    def illumination_assemblies(self) -> dict[str, IlluminationPathDefinition]:
        """Get the illumination assemblies in the instrument."""
        return self.instrument.assembly.illumination

    def _reset_state(self) -> None:
        """Initializes or resets the builder's internal state."""
        self._channel_name: str | None = None
        self._camera: VoxelCamera | None = None
        self._laser: VoxelLaser | None = None
        self._fw_settings: dict[str, tuple[VoxelFilterWheel, str]] = {}  # {fw_name: (fw_obj, filter_name)}
        self._aux_devices: dict[str, VoxelDevice] = {}  # Auxiliary devices from assemblies
        self._detection_assembly: DetectionPathDefinition | None = None
        self._illumination_assembly: IlluminationPathDefinition | None = None
        # Potentially other settings for the channel
        self._channel_specific_settings: dict[str, SettingsBlock] = {}  # {setting_name: setting_block}

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

        assembly = self.instrument.assembly.detection.get(camera_name)
        if not assembly:
            raise ValueError(f"No detection assembly defined for camera '{camera_name}'.")

        self._camera = camera
        self._detection_assembly = assembly
        # Automatically add auxiliary devices from this assembly
        self._add_aux_devices(assembly.aux_devices)
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

        assembly = self.instrument.assembly.illumination.get(laser_name)
        if not assembly:
            raise ValueError(f"No illumination assembly defined for laser '{laser_name}'.")

        self._laser = laser
        self._illumination_assembly = assembly
        # Automatically add auxiliary devices from this assembly
        self._add_aux_devices(assembly.aux_devices)
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

    def add_setting(self, device_name: str, prop_name: str, setting: ZPoint) -> Self:
        """Adds a generic device setting block for the channel (more advanced)."""
        all_device_names = [device.name for device in (self._camera, self._laser) if device] + list(self._aux_devices)
        if device_name not in all_device_names:
            raise ValueError(f"Device '{device_name}' is not part of the current channel configuration.")
        if device_name in self._channel_specific_settings:
            settings = self._channel_specific_settings[device_name]
            if prop_name in settings:
                z_setting = settings[prop_name]
                z_setting.add_point(setting)
            else:
                settings[prop_name] = ZSetting(points=[setting])
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
        config = ChannelConfiguration(
            detection=self._camera.name,
            illumination=self._laser.name,
            filters={fw: filt for fw, (_, filt) in self._fw_settings.items()},
            settings=self._channel_specific_settings,
        )

        channel = Channel.from_config(config=config, channel_name=self._channel_name, instrument=self.instrument)

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
