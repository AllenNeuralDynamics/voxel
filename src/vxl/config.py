import datetime
from pathlib import Path
from typing import Any, Self

from ome_zarr_writer.types import Compression, ScaleLevel
from pydantic import BaseModel, Field, field_validator, model_validator
from vxlib.quantity import NormalizedRange

from rigup import CommandRequest, RigConfig
from vxl.camera.base import SensorROI
from vxl.daq import FrameTiming, Waveform
from vxl.metadata import BASE_METADATA_SCHEMA
from vxl.stack import Stack, StackOrder


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


class SyncTaskConfig(BaseModel):
    """Sync task timing and waveform data (without port assignments)."""

    timing: FrameTiming
    waveforms: dict[str, Waveform]
    stack_only: list[str] = Field(default_factory=list)

    def get_waveforms(self, for_stack: bool = False) -> dict[str, Waveform]:
        """Get waveforms filtered by mode. Stack mode gets all, frame mode excludes stack_only."""
        if for_stack:
            return self.waveforms
        return {k: v for k, v in self.waveforms.items() if k not in self.stack_only}

    @model_validator(mode="before")
    @classmethod
    def insert_missing_windows(cls, m: Any) -> Any:
        waveforms = m.get("waveforms", {})
        timing = m.get("timing")
        if timing is None:
            return m
        duration = timing.get("duration") if isinstance(timing, dict) else getattr(timing, "duration", None)
        if duration is None:
            return m
        for wf in waveforms.values():
            if isinstance(wf, dict) and "window" not in wf:
                wf["window"] = NormalizedRange()
        return m


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
    channels: list[str]
    daq: SyncTaskConfig
    props: dict[str, dict[str, Any]] = Field(default_factory=dict)
    setup: dict[str, list[CommandRequest]] = Field(default_factory=dict)
    rois: dict[str, SensorROI] = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None


class MicroscopeConfig(BaseModel):
    """Configuration for a light sheet microscope.

    Embeds a :class:`RigConfig` for hardware and adds microscope-specific
    sections that mirror VoxelRigConfig.
    """

    rig: RigConfig = Field(default_factory=RigConfig)
    daq: DaqConfig
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

        device_ids.update(profile.daq.waveforms.keys())
        return device_ids

    @model_validator(mode="after")
    def validate_device_references(self) -> Self:
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
        devices = self.device_uids
        errors = []
        if self.daq.device not in devices:
            errors.append(f"DAQ device '{self.daq.device}' not found in devices")
        return errors

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

    def _validate_profile_references(self) -> list[str]:  # noqa: C901
        errors = []
        for profile_id, profile in self.profiles.items():
            if len(profile.channels) == 0:
                errors.append(f"Profile '{profile_id}' must contain at least one channel")
                continue

            for ch_id in profile.channels:
                if ch_id not in self.channels:
                    errors.append(f"Profile '{profile_id}' references channel '{ch_id}' which does not exist")

            duplicates = [ch for ch in set(profile.channels) if profile.channels.count(ch) > 1]
            if duplicates:
                errors.append(f"Profile '{profile_id}' contains duplicate channels: {duplicates}")

            detection_paths: dict[str, str] = {}
            for ch_id in profile.channels:
                if ch_id not in self.channels:
                    continue
                channel = self.channels[ch_id]
                if channel.detection in detection_paths:
                    errors.append(
                        f"Profile '{profile_id}' has channels '{detection_paths[channel.detection]}' and "
                        f"'{ch_id}' both using detection path '{channel.detection}' - "
                        f"channels in a profile must use different cameras",
                    )
                else:
                    detection_paths[channel.detection] = ch_id

            filter_positions: dict[str, dict[str, list[str]]] = {}
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

            for fw_id, positions in filter_positions.items():
                if len(positions) > 1:
                    position_details = ", ".join(
                        [f"'{label}' by channel(s) {channels}" for label, channels in positions.items()],
                    )
                    errors.append(
                        f"Profile '{profile_id}' has conflicting filter positions for '{fw_id}': {position_details}",
                    )

            profile_devices = self.get_profile_device_ids(profile_id)
            daq_acq_devices = set(self.daq.acq_ports.keys())
            devices_needing_waveforms = profile_devices & daq_acq_devices

            missing_waveforms = devices_needing_waveforms - set(profile.daq.waveforms.keys())
            if missing_waveforms:
                errors.append(
                    f"Profile '{profile_id}' missing waveforms for devices in daq.acq_ports: "
                    f"{sorted(missing_waveforms)}",
                )

            extra_waveforms = set(profile.daq.waveforms.keys()) - daq_acq_devices
            if extra_waveforms:
                errors.append(
                    f"Profile '{profile_id}' defines waveforms for devices not in daq.acq_ports: "
                    f"{sorted(extra_waveforms)}",
                )

            settable_devices = profile_devices - self.filter_wheels
            for device_id in profile.props:
                if device_id not in settable_devices:
                    errors.append(
                        f"Profile '{profile_id}' props references '{device_id}' "
                        f"which is not a settable device for this profile",
                    )
            for device_id in profile.setup:
                if device_id not in settable_devices:
                    errors.append(
                        f"Profile '{profile_id}' setup references '{device_id}' "
                        f"which is not a settable device for this profile",
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


# consider nesting output and grid inside of 'plan'?


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
