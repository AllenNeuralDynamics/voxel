import datetime
from pathlib import Path
from typing import Any, Self

from ome_zarr_writer.types import Compression, ScaleLevel
from pydantic import BaseModel, Field, field_validator, model_validator

from rigup import CommandRequest, RigConfig
from vxl.analog_out import AOSignals
from vxl.camera.base import SensorROI
from vxl.metadata import BASE_METADATA_SCHEMA
from vxl.stack import Stack, StackOrder


class StageConfig(BaseModel):
    x: str
    y: str
    z: str


class OpticalPathConfig(BaseModel):
    aux_devices: list[str] = Field(default_factory=list)


class DetectionPathConfig(OpticalPathConfig):
    filter_wheels: list[str]
    magnification: float = Field(..., gt=0, description="Optical magnification of the detection path")
    rotation_deg: int = Field(0, description="Camera rotation relative to stage axes (multiple of 90)")

    @field_validator("rotation_deg")
    @classmethod
    def _validate_rotation(cls, v: int) -> int:
        if v % 90 != 0:
            raise ValueError(f"rotation_deg must be a multiple of 90, got {v}")
        return v


class IlluminationPathConfig(OpticalPathConfig): ...


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


class GridConfig(BaseModel):
    """Grid configuration for 2D tile planning. All positions in micrometers (µm)."""

    x_offset: float = 0.0
    y_offset: float = 0.0
    overlap_x: float = Field(default=0.1, ge=0.0, lt=1.0)
    overlap_y: float = Field(default=0.1, ge=0.0, lt=1.0)

    @model_validator(mode="before")
    @classmethod
    def migrate_overlap(cls, data: Any) -> Any:
        """Migrate single 'overlap' field to overlap_x/overlap_y."""
        if isinstance(data, dict) and "overlap" in data:
            overlap = data.pop("overlap")
            data.setdefault("overlap_x", overlap)
            data.setdefault("overlap_y", overlap)
        return data


class ProfileConfig(BaseModel):
    """A named microscope profile: which channels + how each AO device drives signals.

    ``sync`` is keyed by AO device UID. Each entry is a full ``AOSignals`` config.
    A profile may drive any subset of the AO devices present in the rig.
    """

    channels: list[str]
    sync: dict[str, AOSignals] = Field(default_factory=dict)
    props: dict[str, dict[str, Any]] = Field(default_factory=dict)
    setup: dict[str, list[CommandRequest]] = Field(default_factory=dict)
    rois: dict[str, SensorROI] = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None


class MicroscopeConfig(BaseModel):
    """Configuration for a light sheet microscope.

    Embeds a :class:`RigConfig` for hardware and adds microscope-specific
    sections. AO devices live in ``rig.devices`` with their own ``ports`` /
    ``triggers`` init args — there is no separate top-level DAQ block.
    """

    rig: RigConfig = Field(default_factory=RigConfig)
    stage: StageConfig
    detection: dict[str, DetectionPathConfig]
    illumination: dict[str, IlluminationPathConfig]
    channels: dict[str, ChannelConfig] = Field(default_factory=dict)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

    @property
    def device_uids(self) -> set[str]:
        node_devices = {did for node in self.rig.nodes.values() for did in node.devices}
        return node_devices | set(self.rig.devices.keys())

    @property
    def filter_wheels(self) -> set[str]:
        fws: set[str] = set()
        for path in self.detection.values():
            fws.update(path.filter_wheels)
        return fws

    def get_profile_device_ids(self, profile_id: str) -> set[str]:
        if profile_id not in self.profiles:
            raise KeyError(f"Profile '{profile_id}' not found")

        profile = self.profiles[profile_id]
        device_ids: set[str] = set()

        for channel_id in profile.channels:
            if channel_id not in self.channels:
                continue
            channel = self.channels[channel_id]
            device_ids.add(channel.detection)
            device_ids.add(channel.illumination)
            device_ids.update(channel.filters.keys())
            if channel.detection in self.detection:
                device_ids.update(self.detection[channel.detection].aux_devices)
            if channel.illumination in self.illumination:
                device_ids.update(self.illumination[channel.illumination].aux_devices)

        # Every waveform key in every AO-signals block pulls in that device too
        for ao_signals in profile.sync.values():
            device_ids.update(ao_signals.waveforms.keys())
        return device_ids

    @model_validator(mode="after")
    def validate_device_references(self) -> Self:
        errors = []
        errors.extend(self._validate_stage_references())
        errors.extend(self._validate_path_references())
        errors.extend(self._validate_channel_references())
        errors.extend(self._validate_profile_references())
        if errors:
            raise ValueError("\n".join(errors))
        return self

    def _validate_stage_references(self) -> list[str]:
        devices = self.device_uids
        errors = []
        for axis_name in ["x", "y", "z"]:
            axis_device = getattr(self.stage, axis_name)
            if axis_device not in devices:
                errors.append(f"Stage axis '{axis_name}' device '{axis_device}' not found in devices")
        return errors

    def _validate_path_references(self) -> list[str]:
        devices = self.device_uids
        errors = []
        for device_id in self.detection:
            if device_id not in devices:
                errors.append(f"Detection path '{device_id}' not found in devices")
        for device_id in self.illumination:
            if device_id not in devices:
                errors.append(f"Illumination path '{device_id}' not found in devices")
        for path_id, path in self.detection.items():
            for fw in path.filter_wheels:
                if fw not in devices:
                    errors.append(f"Filter wheel '{fw}' in detection path '{path_id}' not found in devices")
            for aux in path.aux_devices:
                if aux not in devices:
                    errors.append(f"Aux device '{aux}' in detection path '{path_id}' not found in devices")
        for path_id, path in self.illumination.items():
            for aux in path.aux_devices:
                if aux not in devices:
                    errors.append(f"Aux device '{aux}' in illumination path '{path_id}' not found in devices")
        return errors

    def _validate_channel_references(self) -> list[str]:
        devices = self.device_uids
        errors = []
        for channel_id, channel in self.channels.items():
            if channel.detection not in self.detection:
                errors.append(
                    f"Channel '{channel_id}' references detection path '{channel.detection}' which does not exist",
                )
            if channel.illumination not in self.illumination:
                errors.append(
                    f"Channel '{channel_id}' references illumination path "
                    f"'{channel.illumination}' which does not exist",
                )
            for fw_id in channel.filters:
                if fw_id not in devices:
                    errors.append(
                        f"Channel '{channel_id}' references filter wheel '{fw_id}' which does not exist in devices",
                    )
                    continue
                if channel.detection in self.detection:
                    detection_path = self.detection[channel.detection]
                    if fw_id not in detection_path.filter_wheels:
                        errors.append(
                            f"Channel '{channel_id}' references filter wheel '{fw_id}' "
                            f"which is not in detection path '{channel.detection}'",
                        )
        return errors

    def _validate_profile_references(self) -> list[str]:
        """Run per-profile consistency checks and return a flat list of errors."""
        errors: list[str] = []
        devices = self.device_uids
        for profile_id, profile in self.profiles.items():
            if not profile.channels:
                errors.append(f"Profile '{profile_id}' must contain at least one channel")
                continue
            errors.extend(self._validate_profile_channels_exist(profile_id, profile))
            errors.extend(self._validate_profile_no_duplicate_channels(profile_id, profile))
            errors.extend(self._validate_profile_detection_uniqueness(profile_id, profile))
            errors.extend(self._validate_profile_filter_consistency(profile_id, profile))
            errors.extend(self._validate_profile_sync_ao_devices(profile_id, profile, devices))
            settable = self.get_profile_device_ids(profile_id) - self.filter_wheels
            errors.extend(self._validate_profile_props_setup(profile_id, profile, settable))
        return errors

    def _validate_profile_channels_exist(self, profile_id: str, profile: "ProfileConfig") -> list[str]:
        return [
            f"Profile '{profile_id}' references channel '{ch_id}' which does not exist"
            for ch_id in profile.channels
            if ch_id not in self.channels
        ]

    @staticmethod
    def _validate_profile_no_duplicate_channels(profile_id: str, profile: "ProfileConfig") -> list[str]:
        duplicates = [ch for ch in set(profile.channels) if profile.channels.count(ch) > 1]
        if duplicates:
            return [f"Profile '{profile_id}' contains duplicate channels: {duplicates}"]
        return []

    def _validate_profile_detection_uniqueness(self, profile_id: str, profile: "ProfileConfig") -> list[str]:
        """Each detection path may be used by at most one channel within a profile."""
        errors: list[str] = []
        detection_paths: dict[str, str] = {}
        for ch_id in profile.channels:
            channel = self.channels.get(ch_id)
            if channel is None:
                continue
            if channel.detection in detection_paths:
                errors.append(
                    f"Profile '{profile_id}' has channels '{detection_paths[channel.detection]}' and "
                    f"'{ch_id}' both using detection path '{channel.detection}' - "
                    f"channels in a profile must use different cameras",
                )
            else:
                detection_paths[channel.detection] = ch_id
        return errors

    def _validate_profile_filter_consistency(self, profile_id: str, profile: "ProfileConfig") -> list[str]:
        """A filter wheel can only sit at one position across all channels in the profile."""
        filter_positions: dict[str, dict[str, list[str]]] = {}
        for ch_id in profile.channels:
            channel = self.channels.get(ch_id)
            if channel is None:
                continue
            for fw_id, filter_label in channel.filters.items():
                filter_positions.setdefault(fw_id, {}).setdefault(filter_label, []).append(ch_id)

        errors: list[str] = []
        for fw_id, positions in filter_positions.items():
            if len(positions) > 1:
                details = ", ".join([f"'{label}' by channel(s) {channels}" for label, channels in positions.items()])
                errors.append(f"Profile '{profile_id}' has conflicting filter positions for '{fw_id}': {details}")
        return errors

    @staticmethod
    def _validate_profile_sync_ao_devices(profile_id: str, profile: "ProfileConfig", devices: set[str]) -> list[str]:
        return [
            f"Profile '{profile_id}' sync references AO device '{ao_uid}' which is not in rig.devices"
            for ao_uid in profile.sync
            if ao_uid not in devices
        ]

    @staticmethod
    def _validate_profile_props_setup(profile_id: str, profile: "ProfileConfig", settable: set[str]) -> list[str]:
        errors: list[str] = []
        for device_id in profile.props:
            if device_id not in settable:
                errors.append(
                    f"Profile '{profile_id}' props references '{device_id}' "
                    f"which is not a settable device for this profile"
                )
        for device_id in profile.setup:
            if device_id not in settable:
                errors.append(
                    f"Profile '{profile_id}' setup references '{device_id}' "
                    f"which is not a settable device for this profile"
                )
        return errors


class PlanConfig(BaseModel):
    profile_order: list[str] = Field(default_factory=list)
    stack_order: StackOrder = StackOrder.SNAKE_ROW
    sort_by_profile: bool = False
    z_step: float = 1.0  # default Z step in µm
    default_z_start: float = 0.0  # default Z start for new stacks (µm)
    default_z_end: float = 511.0  # default Z end for new stacks (µm) — 512 frames at 1µm step

    def has_profile(self, profile_id: str) -> bool:
        """Check if a profile is in the plan."""
        return profile_id in self.profile_order


class OutputConfig(BaseModel):
    # Storage settings. store_path is resolved by Session.store_path
    # (prefers info.data_path when set). batch_z_shards and target_shard_gb
    # are intentionally NOT persisted here — they're runtime pipeline knobs
    # supplied by the rig (see rig.py constants).
    store_path: Path = Field(
        default=Path("./data"), description="Path for acquired data (relative to session dir or absolute)"
    )
    max_level: ScaleLevel = Field(default=ScaleLevel.L3, description="Maximum pyramid downscale level")
    compression: Compression = Field(default=Compression.BLOSC_LZ4, description="Compression codec for zarr chunks")


class SessionInfo(BaseModel):
    """Session identity, provenance, and lifecycle metadata."""

    # Identity
    uid: str = ""
    name: str = ""
    description: str = ""

    # Provenance
    source: str = ""  # template name or source session UID
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.UTC))
    created_by: str = ""  # operator / username
    hostname: str = ""  # machine name

    # Data location
    data_root: str = ""  # DataRoot.name chosen at creation
    data_path: str = ""  # resolved absolute path at creation time

    # Organization
    collection: str = ""  # user-defined grouping

    # Lifecycle
    last_opened: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.UTC))
    open_count: int = 0


class SessionConfig(MicroscopeConfig):
    """Combined rig configuration and session state.

    This model represents the complete session file (.voxel.yaml) with:
    - rig: The full VoxelRigConfig
    - info: Session identity and lifecycle metadata
    - plan: Traversal ordering + per-stack defaults
    - output: Storage path, pyramid level, compression
    - grid: Grid offsets and overlap
    - stacks: Acquisition stacks (tiles + z-ranges)
    """

    info: SessionInfo
    metadata_schema: str = Field(default=BASE_METADATA_SCHEMA, description="Import path for metadata class")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Experiment metadata values")
    plan: PlanConfig = Field(default_factory=PlanConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    grid: GridConfig = Field(default_factory=GridConfig)
    stacks: dict[str, Stack] = Field(default_factory=dict)
