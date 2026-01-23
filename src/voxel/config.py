from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from pyrig import RigConfig
from voxel.sync import SyncTaskData

TileOrder = Literal["row_wise", "column_wise", "snake_row", "snake_column", "unset"]


class GlobalsConfig(BaseModel):
    """Global settings for acquisition planning."""

    default_overlap: float = Field(default=0.1, ge=0.0, le=0.5, description="Default tile overlap (0.0-0.5)")
    default_tile_order: TileOrder = Field(default="snake_row", description="Default tile ordering pattern")
    default_z_step_um: float = Field(default=1.0, gt=0.0, description="Default z-step in micrometers")


class DaqConfig(BaseModel):
    device: str
    acq_ports: dict[str, str]

    @field_validator("acq_ports")
    @classmethod
    def validate_unique_ports(cls, v: dict[str, str]) -> dict[str, str]:
        ports = list(v.values())
        if len(ports) != len(set(ports)):
            duplicates = [p for p in set(ports) if ports.count(p) > 1]
            raise ValueError(f"Duplicate acq_ports detected: {duplicates}")
        return v


class StageConfig(BaseModel):
    x: str
    y: str
    z: str
    roll: str | None = None
    pitch: str | None = None
    yaw: str | None = None


class OpticalPathConfig(BaseModel):
    aux_devices: list[str] = Field(default_factory=list)


class DetectionPathConfig(OpticalPathConfig):
    filter_wheels: list[str]
    magnification: float = Field(..., gt=0, description="Optical magnification of the detection path")


class IlluminationPathConfig(OpticalPathConfig): ...


class VoxelLayout(BaseModel):
    detection: dict[str, DetectionPathConfig]
    illumination: dict[str, IlluminationPathConfig]


class ChannelConfig(BaseModel):
    detection: str
    illumination: str
    filters: dict[str, str] = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None
    emission: float | None = None  # Peak emission wavelength in nm

    @field_validator("emission")
    @classmethod
    def validate_emission(cls, v: float | None) -> float | None:
        """Validate emission wavelength."""
        if v is not None:
            if v <= 0:
                raise ValueError(f"emission wavelength must be positive, got {v}")
            if v < 200 or v > 2000:
                raise ValueError(f"emission wavelength out of reasonable range: {v} nm")
        return v


class ProfileConfig(BaseModel):
    channels: list[str]
    daq: SyncTaskData
    desc: str = ""
    label: str | None = None


class VoxelRigConfig(RigConfig):
    globals: GlobalsConfig
    daq: DaqConfig
    stage: StageConfig
    detection: dict[str, DetectionPathConfig]
    illumination: dict[str, IlluminationPathConfig]
    channels: dict[str, ChannelConfig] = Field(default_factory=dict)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

    @property
    def filter_wheels(self) -> set[str]:
        """Get all filter wheel device IDs from all detection paths."""
        fws: set[str] = set()
        for path in self.detection.values():
            fws.update(path.filter_wheels)
        return fws

    def get_profile_device_ids(self, profile_id: str) -> set[str]:
        """Get all device IDs used by a profile.

        Returns the set of all devices involved in the profile, including:
        - Detection path devices (cameras)
        - Illumination path devices (lasers)
        - Filter wheels used by channels in the profile
        - Aux devices in detection and illumination paths

        Args:
            profile_id: The profile identifier

        Returns:
            Set of device IDs used by the profile

        Raises:
            KeyError: If profile_id does not exist
        """
        if profile_id not in self.profiles:
            raise KeyError(f"Profile '{profile_id}' not found")

        profile = self.profiles[profile_id]
        device_ids: set[str] = set()

        for channel_id in profile.channels:
            if channel_id not in self.channels:
                continue  # Skip invalid channels (will be caught by validation)

            channel = self.channels[channel_id]
            device_ids.add(channel.detection)
            device_ids.add(channel.illumination)
            device_ids.update(channel.filters.keys())
            if channel.detection in self.detection:
                device_ids.update(self.detection[channel.detection].aux_devices)
            if channel.illumination in self.illumination:
                device_ids.update(self.illumination[channel.illumination].aux_devices)

        return device_ids

    @model_validator(mode="after")
    def validate_device_references(self) -> Self:
        """Validate that all device references exist in nodes."""
        errors = []
        errors.extend(self._validate_daq_references())
        errors.extend(self._validate_stage_references())
        errors.extend(self._validate_path_references())
        errors.extend(self._validate_channel_references())
        errors.extend(self._validate_profile_references())

        if errors:
            raise ValueError("\n".join(errors))

        return self

    def _validate_daq_references(self) -> list[str]:
        """Validate DAQ configuration references."""
        devices = self.device_uids
        errors = []

        # Validate DAQ device reference
        if self.daq.device not in devices:
            errors.append(f"DAQ device '{self.daq.device}' not found in devices")

        # Validate DAQ acq_ports reference valid devices
        for device_id in self.daq.acq_ports:
            if device_id not in devices:
                errors.append(f"DAQ acq_port device '{device_id}' not found in devices")

        return errors

    def _validate_path_references(self) -> list[str]:
        """Validate detection and illumination path references."""
        devices = self.device_uids
        errors = []

        # Validate detection paths reference valid devices
        for device_id in self.detection:
            if device_id not in devices:
                errors.append(f"Detection path '{device_id}' not found in devices")

        # Validate illumination paths reference valid devices
        for device_id in self.illumination:
            if device_id not in devices:
                errors.append(f"Illumination path '{device_id}' not found in devices")

        # Validate filter_wheels and aux_devices in detection paths
        for path_id, path in self.detection.items():
            for fw in path.filter_wheels:
                if fw not in devices:
                    errors.append(f"Filter wheel '{fw}' in detection path '{path_id}' not found in devices")
            for aux in path.aux_devices:
                if aux not in devices:
                    errors.append(f"Aux device '{aux}' in detection path '{path_id}' not found in devices")

        # Validate aux_devices in illumination paths
        for path_id, path in self.illumination.items():
            for aux in path.aux_devices:
                if aux not in devices:
                    errors.append(f"Aux device '{aux}' in illumination path '{path_id}' not found in devices")

        return errors

    def _validate_channel_references(self) -> list[str]:
        """Validate channel configuration references."""
        devices = self.device_uids
        errors = []

        for channel_id, channel in self.channels.items():
            # Validate detection path reference
            if channel.detection not in self.detection:
                errors.append(
                    f"Channel '{channel_id}' references detection path '{channel.detection}' which does not exist",
                )

            # Validate illumination path reference
            if channel.illumination not in self.illumination:
                errors.append(
                    f"Channel '{channel_id}' references illumination path "
                    f"'{channel.illumination}' which does not exist",
                )

            # Validate filter wheel references
            for fw_id in channel.filters:
                # Check that filter wheel device exists
                if fw_id not in devices:
                    errors.append(
                        f"Channel '{channel_id}' references filter wheel '{fw_id}' which does not exist in devices",
                    )
                    continue

                # Check that filter wheel is in the detection path
                if channel.detection in self.detection:
                    detection_path = self.detection[channel.detection]
                    if fw_id not in detection_path.filter_wheels:
                        errors.append(
                            f"Channel '{channel_id}' references filter wheel '{fw_id}' "
                            f"which is not in detection path '{channel.detection}'",
                        )

        return errors

    def _validate_profile_references(self) -> list[str]:  # noqa: C901 - validates many cross-references
        """Validate profile configuration references and compatibility."""
        errors = []

        for profile_id, profile in self.profiles.items():
            # 1. Non-empty channels list
            if len(profile.channels) == 0:
                errors.append(f"Profile '{profile_id}' must contain at least one channel")
                continue

            # 2. Channel existence
            for ch_id in profile.channels:
                if ch_id not in self.channels:
                    errors.append(f"Profile '{profile_id}' references channel '{ch_id}' which does not exist")

            # 3. No duplicate channels within profile
            duplicates = [ch for ch in set(profile.channels) if profile.channels.count(ch) > 1]
            if duplicates:
                errors.append(f"Profile '{profile_id}' contains duplicate channels: {duplicates}")

            # 4. Unique detection paths (cameras cannot be shared in a profile)
            detection_paths: dict[str, str] = {}  # detection_path -> channel_id
            for ch_id in profile.channels:
                if ch_id not in self.channels:
                    continue  # Already reported above
                channel = self.channels[ch_id]
                if channel.detection in detection_paths:
                    errors.append(
                        f"Profile '{profile_id}' has channels '{detection_paths[channel.detection]}' and "
                        f"'{ch_id}' both using detection path '{channel.detection}' - "
                        f"channels in a profile must use different cameras",
                    )
                else:
                    detection_paths[channel.detection] = ch_id

            # 5. Shared filter wheel consistency (same wheel must be at same position)
            filter_positions: dict[str, dict[str, list[str]]] = {}  # fw_id -> {filter_label: [channel_ids]}
            for ch_id in profile.channels:
                if ch_id not in self.channels:
                    continue
                channel = self.channels[ch_id]
                for fw_id, filter_label in channel.filters.items():
                    if fw_id not in filter_positions:
                        filter_positions[fw_id] = {}
                    if filter_label not in filter_positions[fw_id]:
                        filter_positions[fw_id][filter_label] = []
                    filter_positions[fw_id][filter_label].append(ch_id)

            # Check for conflicts (same filter wheel, different positions)
            for fw_id, positions in filter_positions.items():
                if len(positions) > 1:  # Multiple different positions for same wheel
                    position_details = ", ".join(
                        [f"'{label}' by channel(s) {channels}" for label, channels in positions.items()],
                    )
                    errors.append(
                        f"Profile '{profile_id}' has conflicting filter positions for '{fw_id}': {position_details}",
                    )

            # 6. Waveform validation - check for devices in both daq.acq_ports AND used by profile
            profile_devices = self.get_profile_device_ids(profile_id)
            daq_acq_devices = set(self.daq.acq_ports.keys())
            devices_needing_waveforms = profile_devices & daq_acq_devices

            # Check for missing waveforms
            missing_waveforms = devices_needing_waveforms - set(profile.daq.waveforms.keys())
            if missing_waveforms:
                errors.append(
                    f"Profile '{profile_id}' missing waveforms for devices in daq.acq_ports: "
                    f"{sorted(missing_waveforms)}",
                )

            # Check for extra waveforms (not in acq_ports)
            extra_waveforms = set(profile.daq.waveforms.keys()) - daq_acq_devices
            if extra_waveforms:
                errors.append(
                    f"Profile '{profile_id}' defines waveforms for devices not in daq.acq_ports: "
                    f"{sorted(extra_waveforms)}",
                )

        return errors

    def _validate_stage_references(self) -> list[str]:
        """Validate stage axis references."""
        devices = self.device_uids
        errors = []

        if hasattr(self, "stage") and self.stage is not None:
            for axis_name in ["x", "y", "z"]:
                axis_device = getattr(self.stage, axis_name)
                if axis_device not in devices:
                    errors.append(f"Stage axis '{axis_name}' device '{axis_device}' not found in devices")
            for axis_name in ["roll", "pitch", "yaw"]:
                axis_device = getattr(self.stage, axis_name)
                if axis_device is not None and axis_device not in devices:
                    errors.append(f"Stage axis '{axis_name}' device '{axis_device}' not found in devices")

        return errors
