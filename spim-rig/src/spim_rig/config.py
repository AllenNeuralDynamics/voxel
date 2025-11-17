from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from pyrig import RigConfig


class DeviceType(StrEnum):
    DAQ = "daq"
    CAMERA = "camera"
    LASER = "laser"
    FILTER_WHEEL = "filter_wheel"


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


class IlluminationPathConfig(OpticalPathConfig): ...


class SpimLayout(BaseModel):
    detection: dict[str, DetectionPathConfig]
    illumination: dict[str, IlluminationPathConfig]


class ChannelConfig(BaseModel):
    detection: str
    illumination: str
    filters: dict[str, str] = Field(default_factory=dict)
    desc: str = ""


class ProfileConfig(BaseModel):
    channels: list[str]
    desc: str = ""


class SpimRigConfig(RigConfig):
    daq: DaqConfig
    # stage: StageConfig
    detection: dict[str, DetectionPathConfig]
    illumination: dict[str, IlluminationPathConfig]
    channels: dict[str, ChannelConfig] = Field(default_factory=dict)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_device_references(self) -> Self:
        """Validate that all device references exist in nodes."""
        errors = []
        errors.extend(self._validate_daq_references())
        # errors.extend(self._validate_stage_references())
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
                    f"Channel '{channel_id}' references detection path '{channel.detection}' which does not exist"
                )

            # Validate illumination path reference
            if channel.illumination not in self.illumination:
                errors.append(
                    f"Channel '{channel_id}' references illumination path '{channel.illumination}' which does not exist"
                )

            # Validate filter wheel references
            for fw_id, filter_label in channel.filters.items():
                # Check that filter wheel device exists
                if fw_id not in devices:
                    errors.append(
                        f"Channel '{channel_id}' references filter wheel '{fw_id}' which does not exist in devices"
                    )
                    continue

                # Check that filter wheel is in the detection path
                if channel.detection in self.detection:
                    detection_path = self.detection[channel.detection]
                    if fw_id not in detection_path.filter_wheels:
                        errors.append(
                            f"Channel '{channel_id}' references filter wheel '{fw_id}' "
                            f"which is not in detection path '{channel.detection}'"
                        )

        return errors

    def _validate_profile_references(self) -> list[str]:
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
                        f"Profile '{profile_id}' has channels '{detection_paths[channel.detection]}' and '{ch_id}' "
                        f"both using detection path '{channel.detection}' - channels in a profile must use different cameras"
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
                        [f"'{label}' by channel(s) {channels}" for label, channels in positions.items()]
                    )
                    errors.append(
                        f"Profile '{profile_id}' has conflicting filter positions for '{fw_id}': {position_details}"
                    )

        return errors

    # def _validate_stage_references(self) -> list[str]:
    #     """Validate stage axis references."""
    #     devices = self.device_uids
    #     errors = []
    #
    #     if hasattr(self, "stage") and self.stage is not None:
    #         for axis_name in ["x", "y", "z"]:
    #             axis_device = getattr(self.stage, axis_name)
    #             if axis_device not in devices:
    #                 errors.append(f"Stage axis '{axis_name}' device '{axis_device}' not found in devices")
    #         for axis_name in ["roll", "pitch", "yaw"]:
    #             axis_device = getattr(self.stage, axis_name)
    #             if axis_device is not None and axis_device not in devices:
    #                 errors.append(f"Stage axis '{axis_name}' device '{axis_device}' not found in devices")
    #
    #     return errors
