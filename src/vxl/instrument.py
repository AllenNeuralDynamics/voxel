import asyncio
import datetime
import getpass
import logging
import math
import uuid
from collections.abc import Callable, Collection, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Self

from ome_zarr_writer import Compression, DownscaleType, ScaleLevel, WriterSettings
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator

from rigup import CommandRequest, DeviceHandle, Rig, RigConfig
from vxl.system import System, load_yaml, save_yaml
from vxlib import (
    Cell,
    Color,
    Computed,
    Emitter,
    ReactiveQuery,
    Readable,
    SchemaModel,
    Subscribable,
    Teardown,
    atomic_write,
)

from .axes import ContinuousAxisHandle, StepMode, TTLStepperConfig
from .camera import CameraHandle, CaptureState, PreviewLevels, PreviewViewport, SensorROI, StorageSpec
from .daq.analog import AOHandle, AOSignals
from .metadata import ExperimentMetadata, MetadataCls, resolve_metadata_class
from .traversal import Tile, TileOrder

logger = logging.getLogger(__name__)


class Patch(BaseModel):
    """Base for partial-update models: only the fields the caller explicitly set are applied.

    ``extra="forbid"`` rejects unknown keys at construction, so a typo'd field fails loudly at the
    boundary instead of being silently dropped. :meth:`changes` returns exactly the set fields
    (including any explicitly set to ``None``, so a nullable field can be cleared).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class StageConfig(SchemaModel):
    x: str
    y: str
    z: str


class OpticalPathConfig(SchemaModel):
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


class HALConfig(RigConfig, frozen=True):
    """The hardware blueprint: a rig (``devices`` + ``nodes``, inherited) plus the microscope wiring
    (stage axes, detection/illumination paths). Immutable — loaded once, never edited at runtime."""

    stage: StageConfig
    detection: dict[str, DetectionPathConfig]
    illumination: dict[str, IlluminationPathConfig]

    @property
    def device_uids(self) -> set[str]:
        node_devices = {did for node in self.nodes.values() for did in node.devices}
        return node_devices | set(self.devices.keys())

    @property
    def filter_wheels(self) -> set[str]:
        fws: set[str] = set()
        for path in self.detection.values():
            fws.update(path.filter_wheels)
        return fws

    @model_validator(mode="after")
    def validate_device_references(self) -> Self:
        errors = self._validate_stage_references() + self._validate_path_references()
        if errors:
            raise ValueError("\n".join(errors))
        return self

    def _validate_stage_references(self) -> list[str]:
        devices = self.device_uids
        errors = []

        # Explicit mapping ensures type-safety and allows safe IDE refactoring
        stage_axes = {"x": self.stage.x, "y": self.stage.y, "z": self.stage.z}

        for axis_name, axis_device in stage_axes.items():
            if axis_device not in devices:
                errors.append(f"Stage axis '{axis_name}' device '{axis_device}' not found in devices")

        return errors

    def _validate_path_references(self) -> list[str]:
        devices = self.device_uids
        errors = []

        for path_id, path in self.detection.items():
            if path_id not in devices:
                errors.append(f"Detection path '{path_id}' not found in devices")
            for fw in path.filter_wheels:
                if fw not in devices:
                    errors.append(f"Filter wheel '{fw}' in detection path '{path_id}' not found in devices")
            for aux in path.aux_devices:
                if aux not in devices:
                    errors.append(f"Aux device '{aux}' in detection path '{path_id}' not found in devices")

        for path_id, path in self.illumination.items():
            if path_id not in devices:
                errors.append(f"Illumination path '{path_id}' not found in devices")
            for aux in path.aux_devices:
                if aux not in devices:
                    errors.append(f"Aux device '{aux}' in illumination path '{path_id}' not found in devices")

        return errors


@dataclass(frozen=True)
class Stage:
    x: ContinuousAxisHandle
    y: ContinuousAxisHandle
    z: ContinuousAxisHandle

    @property
    def scanning_axis(self) -> ContinuousAxisHandle:
        return self.z


class HAL:
    """Runtime hardware abstraction: opens the rig and exposes typed device handles."""

    def __init__(self, config: HALConfig, name: str = "VoxelHAL") -> None:
        self._cfg = config
        self._rig = Rig(config, name)

        self.cameras: dict[str, CameraHandle] = {}
        self.lasers: dict[str, DeviceHandle] = {}
        self.aotfs: dict[str, DeviceHandle] = {}
        self.continuous_axes: dict[str, ContinuousAxisHandle] = {}
        self.discrete_axes: dict[str, DeviceHandle] = {}
        self.fws: dict[str, DeviceHandle] = {}
        self.analog_outs: dict[str, AOHandle] = {}
        self._stage: Stage | None = None

    @property
    def config(self) -> HALConfig:
        return self._cfg

    @property
    def rig(self) -> Rig:
        return self._rig

    @property
    def devices(self) -> dict[str, DeviceHandle]:
        return self.rig.devices

    @property
    def stage(self) -> Stage:
        if self._stage is None:
            raise RuntimeError("HAL is not open — stage is unavailable")
        return self._stage

    async def open(self) -> None:
        await self._rig.open()
        for uid, handle in self.rig.devices.items():
            device_type = (await handle.interface()).type
            match device_type:
                case "camera":
                    self.cameras[uid] = CameraHandle.wrap(handle)
                case "daq_ao":
                    self.analog_outs[uid] = AOHandle.wrap(handle)
                case "laser":
                    self.lasers[uid] = handle
                case "aotf":
                    self.aotfs[uid] = handle
                case "continuous_axis":
                    self.continuous_axes[uid] = ContinuousAxisHandle.wrap(handle)
                case "discrete_axis":
                    self.discrete_axes[uid] = handle
                case _:
                    logger.debug("Uncategorized device '%s' of type '%s'", uid, device_type)

        for fw_id in self._cfg.filter_wheels:
            if fw_id in self.rig.devices:
                self.fws[fw_id] = self.rig.devices[fw_id]

        # Gather validation errors at initialization
        errors = (
            self._validate_camera_paths()
            + self._validate_laser_paths()
            + self._validate_stage_axes()
            + self._validate_filter_wheels()
            + self._validate_aux_not_reserved()
        )
        if errors:
            raise ValueError("Microscope device validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

        # Prime each camera's cached property values (pixel_size_um, sensor_size_px, ...)
        await asyncio.gather(*(camera.props.prime() for camera in self.cameras.values()))

        self._stage = Stage(
            x=self.continuous_axes[self._cfg.stage.x],
            y=self.continuous_axes[self._cfg.stage.y],
            z=self.continuous_axes[self._cfg.stage.z],
        )

    async def close(self) -> None:
        self._stage = None
        self.cameras.clear()
        self.lasers.clear()
        self.aotfs.clear()
        self.continuous_axes.clear()
        self.discrete_axes.clear()
        self.fws.clear()
        self.analog_outs.clear()
        await self._rig.close()

    def _validate_camera_paths(self) -> list[str]:
        errors = []
        camera_ids = set(self.cameras.keys())
        detection_ids = set(self._cfg.detection.keys())
        if missing := camera_ids - detection_ids:
            errors.append(f"Cameras without detection paths: {missing}")
        if invalid := detection_ids - camera_ids:
            errors.append(f"Detection paths referencing non-camera devices: {invalid}")
        return errors

    def _validate_laser_paths(self) -> list[str]:
        errors = []
        laser_ids = set(self.lasers.keys())
        illumination_ids = set(self._cfg.illumination.keys())
        if missing := laser_ids - illumination_ids:
            errors.append(f"Lasers without illumination paths: {missing}")
        if invalid := illumination_ids - laser_ids:
            errors.append(f"Illumination paths referencing non-laser devices: {invalid}")
        return errors

    def _validate_stage_axes(self) -> list[str]:
        stage_cfg = self._cfg.stage
        if invalid := {stage_cfg.x, stage_cfg.y, stage_cfg.z} - set(self.continuous_axes.keys()):
            return [f"Stage axes are not continuous_axis devices: {invalid}"]
        return []

    def _validate_filter_wheels(self) -> list[str]:
        if invalid := set(self._cfg.filter_wheels) - set(self.discrete_axes.keys()):
            return [f"Filter wheels are not discrete_axis devices: {invalid}"]
        return []

    def _validate_aux_not_reserved(self) -> list[str]:
        # Centralized check for all aux devices across all paths
        reserved = (
            set(self.cameras.keys())
            | set(self.lasers.keys())
            | set(self._cfg.filter_wheels)
            | {self._cfg.stage.x, self._cfg.stage.y, self._cfg.stage.z}
            | set(self.analog_outs.keys())
        )

        errors = []
        path_groups = [("detection", self._cfg.detection), ("illumination", self._cfg.illumination)]
        for path_type, paths in path_groups:
            for path_id, path in paths.items():
                for aux in path.aux_devices:
                    if aux in reserved:
                        errors.append(f"Aux device '{aux}' in {path_type} path '{path_id}' is a reserved type.")
        return errors


class ChannelConfig(SchemaModel):
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
        if v is not None and not (200 <= v <= 2000):
            raise ValueError(f"emission wavelength out of reasonable range: {v} nm")
        return v

    @property
    def colormap(self) -> str:
        """Colormap from emission wavelength; ``'white'`` fallback (incl. non-visible wavelengths)."""
        if not self.emission:
            return "white"
        color = str(Color.from_wavelength(self.emission))
        return color if color != "#000000" else "white"  # from_wavelength yields black outside 380-780 nm


class ChannelPatch(Patch):
    desc: str | None = None
    label: str | None = None
    emission: float | None = None


class ProfileConfig(SchemaModel):
    """A named microscope profile: which channels + how each AO device drives signals.

    ``sync`` is keyed by AO device UID. Each entry is a full ``AOSignals`` config.
    A profile may drive any subset of the AO devices present in the rig.
    """

    channels: list[str]
    z_step: float = Field(..., gt=0, description="Axial step between frames in µm (one scan-axis move per frame)")
    sync: dict[str, AOSignals] = Field(default_factory=dict)
    props: dict[str, dict[str, Any]] = Field(default_factory=dict)
    setup: dict[str, list[CommandRequest]] = Field(default_factory=dict)
    rois: dict[str, SensorROI] = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None


class ProfilePatch(Patch):
    z_step: Annotated[float, Field(gt=0)] | None = None
    desc: str | None = None
    label: str | None = None


class ProtocolError(Exception):
    """Raised when an edit is rejected (precondition or rig incompatibility); state is unchanged."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


class ImagingProtocol(SchemaModel):
    channels: dict[str, ChannelConfig]
    profiles: dict[str, ProfileConfig]

    def compute_saved_fov(self, profile_ids: Sequence[str], hal: HAL) -> tuple[float, float]:
        """Bounding-box FOV implied by saved profile ROIs and cached HAL geometry.

        This is the planned/saved FOV, not the live camera FOV. Missing profiles, channels, and camera
        geometry are skipped; returns ``(0.0, 0.0)`` when nothing resolves.
        """
        widths: list[float] = []
        heights: list[float] = []
        for pid in profile_ids:
            profile = self.profiles.get(pid)
            if profile is None:
                continue
            for ch_id in profile.channels:
                channel = self.channels.get(ch_id)
                if channel is None:
                    continue
                cam = channel.detection
                camera = hal.cameras.get(cam)
                if camera is None or (pixel_size := camera.pixel_size_um.value) is None:
                    continue
                if (sensor := camera.sensor_size_px.value) is None:
                    continue
                roi = profile.rois.get(cam)
                w_px, h_px = (roi.w, roi.h) if roi is not None else (sensor.x, sensor.y)
                factor = pixel_size / hal.config.detection[cam].magnification
                if hal.config.detection[cam].rotation_deg % 180 == 0:
                    widths.append(w_px * factor.x)
                    heights.append(h_px * factor.y)
                else:
                    widths.append(h_px * factor.y)
                    heights.append(w_px * factor.x)
        return (max(widths, default=0.0), max(heights, default=0.0))

    def get_profile_settable_devices(self, profile_id: str, hal: HALConfig) -> set[str]:
        profile = self.profiles[profile_id]
        ids: set[str] = set()
        for ch_id in profile.channels:
            if (ch := self.channels.get(ch_id)) is None:
                continue
            ids.update({ch.detection, ch.illumination, *ch.filters})
            if ch.detection in hal.detection:
                ids.update(hal.detection[ch.detection].aux_devices)
            if ch.illumination in hal.illumination:
                ids.update(hal.illumination[ch.illumination].aux_devices)
        for ao in profile.sync.values():
            ids.update(ao.waveforms.keys())
        return ids - hal.filter_wheels

    def check_hal_compatibility(self, hal: HALConfig) -> list[str]:
        errors = []
        for ch_id, ch in self.channels.items():
            if ch.detection not in hal.detection:
                errors.append(f"Channel '{ch_id}' missing detection path '{ch.detection}'.")
            if ch.illumination not in hal.illumination:
                errors.append(f"Channel '{ch_id}' missing illumination path '{ch.illumination}'.")

            for fw_id in ch.filters:
                if fw_id not in hal.device_uids:
                    errors.append(f"Channel '{ch_id}' requests filter wheel '{fw_id}', which is not in devices.")
                elif ch.detection in hal.detection and fw_id not in hal.detection[ch.detection].filter_wheels:
                    errors.append(f"Filter wheel '{fw_id}' is not physically wired to detection '{ch.detection}'.")

        for profile_id, profile in self.profiles.items():
            for ao_uid in profile.sync:
                if ao_uid not in hal.device_uids:
                    errors.append(f"Profile '{profile_id}' sync references AO device '{ao_uid}' which is missing.")

            settable = self.get_profile_settable_devices(profile_id, hal)
            # setup runs arbitrary device commands (not props), so it may legitimately target filter
            # wheels — which are intentionally excluded from `settable` (props drive them via select).
            setup_targets = settable | hal.filter_wheels

            for device_id in profile.props:
                if device_id not in settable:
                    errors.append(f"Profile '{profile_id}' props references '{device_id}' (inactive).")

            for device_id in profile.setup:
                if device_id not in setup_targets:
                    errors.append(f"Profile '{profile_id}' setup references '{device_id}' (inactive).")

        return errors

    @field_validator("channels", "profiles")
    @classmethod
    def check_at_least_one[M: ChannelConfig | ProfileConfig](
        cls, v: dict[str, M], info: ValidationInfo
    ) -> dict[str, M]:
        if not v:
            raise ValueError(f"at least one {(info.field_name or 'entry').rstrip('s')} must be present")
        return v

    @model_validator(mode="after")
    def validate_logical_consistency(self) -> Self:
        errors = []
        for profile_id, profile in self.profiles.items():
            if not profile.channels:
                errors.append(f"Profile '{profile_id}' must contain at least one channel.")
                continue

            errors.extend(self._check_duplicate_channels(profile_id, profile))
            errors.extend(self._check_channel_existence(profile_id, profile))

            valid_channel_ids = [ch_id for ch_id in profile.channels if ch_id in self.channels]
            if valid_channel_ids:
                errors.extend(self._check_camera_uniqueness(profile_id, valid_channel_ids))
                errors.extend(self._check_filter_consistency(profile_id, valid_channel_ids))
                errors.extend(self._check_roi_references(profile_id, profile, valid_channel_ids))

        if errors:
            raise ValueError("Logical consistency errors in Protocol:\n- " + "\n- ".join(errors))
        return self

    def _check_duplicate_channels(self, profile_id: str, profile: ProfileConfig) -> list[str]:
        if duplicates := {ch for ch in profile.channels if profile.channels.count(ch) > 1}:
            return [f"Profile '{profile_id}' contains duplicate channels: {list(duplicates)}"]
        return []

    def _check_channel_existence(self, profile_id: str, profile: ProfileConfig) -> list[str]:
        return [
            f"Channel '{ch_id}' referenced in profile '{profile_id}' not found in protocol channels."
            for ch_id in profile.channels
            if ch_id not in self.channels
        ]

    def _check_camera_uniqueness(self, profile_id: str, valid_channel_ids: list[str]) -> list[str]:
        errors, detection_paths = [], {}
        for ch_id in valid_channel_ids:
            channel = self.channels[ch_id]
            if channel.detection in detection_paths:
                errors.append(
                    f"Profile '{profile_id}' conflict: Channels '{detection_paths[channel.detection]}' "
                    f"and '{ch_id}' both use detection path '{channel.detection}'."
                )
            else:
                detection_paths[channel.detection] = ch_id
        return errors

    def _check_filter_consistency(self, profile_id: str, valid_channel_ids: list[str]) -> list[str]:
        errors, filter_positions = [], {}
        for ch_id in valid_channel_ids:
            channel = self.channels[ch_id]
            for fw_id, filter_label in channel.filters.items():
                filter_positions.setdefault(fw_id, {}).setdefault(filter_label, []).append(ch_id)

        for fw_id, positions in filter_positions.items():
            if len(positions) > 1:
                details = ", ".join([f"'{label}' by {chs}" for label, chs in positions.items()])
                errors.append(f"Profile '{profile_id}' commands filter '{fw_id}' to conflicting positions: {details}")
        return errors

    def _check_roi_references(self, profile_id: str, profile: ProfileConfig, valid_channel_ids: list[str]) -> list[str]:
        active_cameras = {self.channels[ch_id].detection for ch_id in valid_channel_ids}
        return [
            f"Profile '{profile_id}' defines an ROI for '{roi_device_id}', but no active channels use it."
            for roi_device_id in profile.rois
            if roi_device_id not in active_cameras
        ]


class Stencil(SchemaModel):
    """Tile-mosaic and z-range defaults prefilled into newly-authored tasks. All positions in micrometers (µm)."""

    x_offset: float = 0.0
    y_offset: float = 0.0
    overlap_x: float = Field(default=0.1, ge=0.0, lt=1.0)
    overlap_y: float = Field(default=0.1, ge=0.0, lt=1.0)

    z_start: float = 0.0
    z_end: float = 511.0

    @model_validator(mode="after")
    def _check_z_range(self) -> Self:
        if self.z_end < self.z_start:
            raise ValueError(f"z_end ({self.z_end}) must be >= z_start ({self.z_start})")
        return self


class StencilPatch(Patch):
    x_offset: float | None = None
    y_offset: float | None = None
    overlap_x: Annotated[float, Field(ge=0.0, lt=1.0)] | None = None
    overlap_y: Annotated[float, Field(ge=0.0, lt=1.0)] | None = None
    z_start: float | None = None
    z_end: float | None = None


class ZStack(SchemaModel):
    x: float
    y: float
    start: float
    end: float

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.end < self.start:
            raise ValueError(f"z-range end ({self.end}) must be >= start ({self.start})")
        return self

    @property
    def signature(self) -> str:
        return f"x{self.x:.2f}_y{self.y:.2f}_z{self.start:.2f}-{self.end:.2f}"

    def num_frames(self, z_step: float) -> int:
        return int((self.end - self.start) / z_step) + 1


class AcquisitionTask(ZStack):
    """A planned acquisition: a stage position (x, y) + z-range, imaged by one or more profiles."""

    profile_ids: list[str] = Field(min_length=1)

    @field_validator("profile_ids")
    @classmethod
    def _dedupe_profile_ids(cls, value: list[str]) -> list[str]:
        """Keep profile_ids unique, preserving order — so appending an existing profile is a no-op."""
        return list(dict.fromkeys(value))

    @property
    def stack(self) -> ZStack:
        return ZStack(x=self.x, y=self.y, start=self.start, end=self.end)


class TaskPatch(Patch):
    x: float | None = None
    y: float | None = None
    start: float | None = None
    end: float | None = None
    profile_ids: list[str] | None = None


class WriterPatch(Patch):
    max_level: ScaleLevel | None = None
    shard_z_chunks: Annotated[int, Field(ge=1)] | None = None
    batch_z_shards: Annotated[int, Field(ge=1)] | None = None
    compression: Compression | None = None
    downscale_type: DownscaleType | None = None
    target_shard_gb: Annotated[float, Field(gt=0)] | None = None


class InstrumentDefaults(SchemaModel):  # everything that can live in config.default
    imaging: ImagingProtocol
    metadata_cls: MetadataCls = ExperimentMetadata
    output: WriterSettings = Field(default_factory=WriterSettings)
    stencil: Stencil = Field(default_factory=Stencil)
    traversal: TileOrder = TileOrder.SNAKE_ROW


PROMOTABLE_FIELDS = frozenset(InstrumentDefaults.model_fields)
"""Baseline fields that ``save_as_default`` / ``restore_default`` can move between bench and config."""


class InstrumentConfig(SchemaModel):
    """A complete instrument spec: the hardware blueprint (:class:`HALConfig`) plus a baseline
    acquisition state (``default``). Shared by shipped ``.voxel.yaml`` templates and each instrument's
    on-disk ``config.yaml`` — a template is just a config without a ``.voxel`` home yet."""

    hal: HALConfig
    default: InstrumentDefaults

    @model_validator(mode="after")
    def check_state_compatibility(self) -> Self:
        if errors := self.default.imaging.check_hal_compatibility(self.hal):
            raise ValueError(", ".join(errors))
        return self

    @classmethod
    def read(cls, path: Path | str) -> Self:
        """Load and validate a config file (a template ``.voxel.yaml`` or an instrument ``config.yaml``)."""
        return load_yaml(Path(path), cls)

    @classmethod
    def discover(cls, root: Path | str) -> dict[str, Self]:
        """Valid configs under ``root`` (``*.voxel.yaml``), keyed by name. Skips unparseable files."""
        root = Path(root)
        if not root.is_dir():
            return {}
        found: dict[str, Self] = {}
        for p_file in sorted(root.glob("*.voxel.yaml")):
            name = p_file.name.removesuffix(".voxel.yaml")
            try:
                found[name] = cls.read(p_file)
            except Exception as e:
                logger.warning("Skipping config '%s': %s", p_file.name, e)
        return found

    def instantiate(self, name: str, into: Path | str) -> Path:
        """Write this config to ``<into>/<name>.voxel/config.yaml``; return the dir. Raises if it exists."""
        directory = Path(into) / f"{name}.voxel"
        if directory.exists():
            raise FileExistsError(f"Instrument '{name}' already exists at {directory}")
        directory.mkdir(parents=True)
        save_yaml(directory / "config.yaml", self)
        return directory


class InstrumentState(InstrumentDefaults):
    """The instrument's editable acquisition state: the imaging protocol (channels + profiles)
    plus planning defaults, traversal, writer options, acquisition tasks, and metadata."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    tasks: dict[str, AcquisitionTask] = Field(default_factory=dict)

    last_modified: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.UTC))

    @model_validator(mode="after")
    def check_task_profile_refs(self) -> Self:
        errors = []
        for task in self.tasks.values():
            for profile_id in task.profile_ids:
                if profile_id not in self.imaging.profiles:
                    errors.append(f"Task profile '{profile_id}' not found in imaging profiles")
        if errors:
            raise ValueError(", ".join(errors))
        return self


type Invariant[T] = Callable[[T], Sequence[str]]


class Bench(Subscribable[InstrumentState]):
    """Validating persistence for one :class:`InstrumentState`."""

    def __init__(self, path: Path, default: InstrumentState, *invariants: Invariant[InstrumentState]) -> None:
        super().__init__()
        self._path = path
        self._invariants = list(invariants)
        self._value = self._load_or_default(default)
        self._lock = asyncio.Lock()

    @property
    def value(self) -> InstrumentState:
        """The current committed state — frozen, safe to hand out without copying."""
        return self._value

    def _load_or_default(self, default: InstrumentState) -> InstrumentState:
        """Load and validate the on-disk bench, falling back to `default` if it is missing, unparseable,
        or rejected by an invariant (e.g. the hardware changed since it was last saved)."""
        if not self._path.exists():
            return default
        try:
            state = InstrumentState.model_validate_json(self._path.read_text(encoding="utf-8"))
        except ValidationError as e:
            logger.warning("Discarding unparseable bench at %s: %s", self._path, e)
            return default
        if violations := self._violations(state):
            logger.warning("Discarding incompatible bench at %s:\n- %s", self._path, "\n- ".join(violations))
            return default
        return state

    def _violations(self, state: InstrumentState) -> list[str]:
        """Every invariant error for `state`, flattened across all registered invariants."""
        return [error for invariant in self._invariants for error in invariant(state)]

    async def _save(self, state: InstrumentState) -> None:
        """Persist `state` to the bench file durably, off the event loop. Writes exactly `state`."""
        await asyncio.to_thread(atomic_write, self._path, state.model_dump_json(indent=2, exclude_none=True))

    async def set(self, candidate: InstrumentState) -> None:
        """Validate, persist, and adopt `candidate`, notifying subscribers with the new state.

        Re-runs the model validators (via a ``model_dump`` round-trip — ``model_copy`` skips them) and the
        registered invariants. Raises :class:`ProtocolError` and changes nothing if either rejects it. A
        candidate identical to the current state (a no-op edit) is dropped before stamping: no save, no
        notify (`last_modified` is excluded from the comparison so an unchanged edit doesn't churn).
        """
        async with self._lock:
            await self._commit(candidate)

    async def update(self, **updates: Any) -> None:
        """Atomically read the current state, patch top-level fields, then validate and persist.

        The read-modify-write runs under the bench lock, so concurrent ``update``/``set`` calls cannot
        interleave into a lost update or a double notify.
        """
        async with self._lock:
            await self._commit(self._value.model_copy(update=updates))

    async def _commit(self, candidate: InstrumentState) -> None:
        """Validate, drop no-ops, check invariants, persist, adopt, and notify. Caller must hold ``_lock``."""
        try:
            validated = InstrumentState.model_validate(candidate.model_dump())
        except ValidationError as e:
            raise ProtocolError([err["msg"] for err in e.errors()]) from e
        if validated.model_copy(update={"last_modified": self._value.last_modified}) == self._value:
            return  # no-op edit (ignoring the timestamp): no save, no notify
        if violations := self._violations(validated):
            raise ProtocolError(violations)
        stamped = validated.model_copy(update={"last_modified": datetime.datetime.now(tz=datetime.UTC)})
        await self._save(stamped)
        self._value = stamped
        await self._notify(stamped)


class AcquisitionMode(StrEnum):
    IDLE = "idle"
    PREVIEW = "preview"
    CAPTURE = "capture"


class Origin(BaseModel):
    on: str = Field(..., description="Machine name of the instrument PC")
    by: str = Field(..., description="Username of the logged-in operator")
    at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.UTC))


class PlannedVolume(BaseModel, frozen=True):
    """One (task, profile) capture in a run's plan — the unit :meth:`Instrument._capture_volume` writes."""

    task: str
    profile: str


class AcquisitionRequest(BaseModel):
    """Parameters of an acquisition run. Shared by the instrument API and the web request body."""

    storage: StorageSpec
    task_ids: list[str] | None = None  # None → every planned task, in traversal order
    operator: str | None = None


class AcquisitionRecord(BaseModel):
    record_id: str = Field(..., exclude=True)
    origin: Origin
    volumes: list[PlannedVolume]
    state: InstrumentState
    hardware: HALConfig


class AcquisitionProgress(BaseModel, frozen=True):
    """One progress update for a (task, profile) volume; emitted per captured batch.

    A profile's channels capture in synchronized batches, so ``frames_done`` is shared across them
    (no per-channel breakdown). Task completion is implicit (``frames_done == frames_total``); the
    run's overall start/stop is conveyed by :attr:`Instrument.mode`.
    """

    task: str
    profile: str
    done: int
    total: int

    def updated(self, *, done: int, total: int | None = None) -> Self:
        return self.model_copy(update={"done": done, "total": total if total is not None else self.total})


class TaskTile(Tile):
    """A task's footprint tile (a :class:`Tile`) tagged with its ``task_id``. Because :class:`TileOrder`
    is generic over the tile subtype, an ordered ``list[TaskTile]`` carries both the per-task geometry
    and the traversal order — replacing a separate tiles-map and order-list with one value."""

    task_id: str


@dataclass(frozen=True)
class Channel:
    """Runtime handles for one protocol channel.

    The channel config remains canonical in :class:`InstrumentState`; this object only holds the
    stable hardware handles resolved from that config.
    """

    uid: str
    camera: CameraHandle
    laser: DeviceHandle

    async def start_preview(self) -> None:
        "Enable this channel's laser and start its camera's preview."
        await self.laser.call("enable")
        await self.camera.start_preview()

    async def stop_preview(self) -> None:
        "Disable this channel's laser and stop its camera's preview."
        await self.laser.call("disable")
        await self.camera.stop_preview()

    async def enable_laser(self) -> None:
        """Enable this channel's laser."""
        await self.laser.call("enable")

    async def disable_laser(self) -> None:
        """Disable this channel's laser."""
        await self.laser.call("disable")


class Instrument:
    """An opened instrument: hardware, persisted acquisition state, and active-profile orchestration."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        cfg = load_yaml(self.config_path, InstrumentConfig)
        self._hal = HAL(cfg.hal, name=f"{self._path.name}")
        self._bench = Bench(
            self._path / "bench.json",
            InstrumentState(**cfg.default.model_dump()),
            lambda state: state.imaging.check_hal_compatibility(self._hal.config),
        )
        self._default = Cell[InstrumentDefaults](cfg.default)
        self._active_profile_id = Cell[str](next(iter(self._bench.value.imaging.profiles)))
        self._channels: dict[str, Channel] = {}
        self._preview_channels: list[Channel] = []
        self._preview_unsubs: list[Teardown] = []
        self._viewport = PreviewViewport()
        self._mode = Cell[AcquisitionMode](AcquisitionMode.IDLE)
        self._preview_epoch = Cell[int](0)
        self._lock = asyncio.Lock()  # Serializes the hardware-driving state machine(s)
        self._acq_task: asyncio.Task[None] | None = None  # the in-flight acquisition run, if any
        self.fov: ReactiveQuery[tuple[float, float]] = ReactiveQuery(fn=self._compute_current_fov)
        self.frames: Emitter[tuple[str, bytes]] = Emitter()
        self.views: Emitter[tuple[str, bytes]] = Emitter()
        self.progress: Emitter[AcquisitionProgress] = Emitter()
        self.task_tiles: Computed[list[TaskTile]] = Computed(self._bench, fn=self._compute_task_tiles)

    @property
    def path(self) -> Path:
        """The instrument's on-disk home (``<name>.voxel/``)."""
        return self._path

    @property
    def config_path(self) -> Path:
        """The instrument's config file path (``<name>.voxel/config.yaml``)."""
        return self._path / "config.yaml"

    @property
    def hal(self) -> HAL:
        return self._hal

    @property
    def state(self) -> Readable[InstrumentState]:
        """Committed acquisition state as a read-only reactive view."""
        return self._bench

    @property
    def default(self) -> Readable[InstrumentDefaults]:
        """The on-disk baseline (``config.yaml`` ``default``) as a reactive view; updated by ``save_as_default``."""
        return self._default

    @property
    def active_profile_id(self) -> Readable[str]:
        """The currently selected profile id. This is always a valid profile key."""
        return self._active_profile_id

    @property
    def preview_epoch(self) -> Readable[int]:
        """Monotonic counter bumped whenever displayed preview frames go stale (e.g. profile switch);
        clients clear their preview when it changes."""
        return self._preview_epoch

    @property
    def active_profile(self) -> ProfileConfig:
        """The current active profile config."""
        return self._bench.value.imaging.profiles[self._active_profile_id.value]

    @property
    def active_channels(self) -> Mapping[str, Channel]:
        """Runtime channels used by the active profile."""
        return {ch_id: self._channels[ch_id] for ch_id in self.active_profile.channels if ch_id in self._channels}

    @property
    def mode(self) -> Readable[AcquisitionMode]:
        """Acquisition mode as a read-only reactive view."""
        return self._mode

    def update_viewport(self, viewport: PreviewViewport | None = None) -> None:
        """Set the shared viewport (no arg = re-apply current) on the active profile's cameras."""
        self._viewport = viewport if viewport is not None else self._viewport
        self._apply_viewport(self.active_channels)

    def _apply_viewport(self, channels: Mapping[str, Channel]) -> None:
        for ch_id, ch in channels.items():
            rot = self._hal.config.detection[self._channel_config(ch_id).detection].rotation_deg
            ch.camera.preview_viewport.update(self._viewport.to_sensor_space(rot) if rot else self._viewport)

    def update_levels(self, levels: dict[str, PreviewLevels]) -> None:
        for ch_id, lvl in levels.items():
            if (ch := self.active_channels.get(ch_id)) is not None:
                ch.camera.preview_levels.update(lvl)

    def update_colormaps(self, colormaps: dict[str, str]) -> None:
        for ch_id, cmap in colormaps.items():
            if (ch := self.active_channels.get(ch_id)) is not None:
                ch.camera.preview_colormap.update(cmap)

    async def open(self) -> None:
        """Open the hardware, activate the default profile, route preview frames, and watch the bench."""
        async with self._lock:
            await self._hal.open()
            self._channels = self._build_channels()
            for camera in self._hal.cameras.values():
                self.fov.add_triggers(camera.frame_area_um)
            await self._apply_profile(self._active_profile_id.value)
            for cam_id, camera in self._hal.cameras.items():
                await self._subscribe_camera(cam_id, camera)
            await self.task_tiles.refresh()

    async def close(self) -> None:
        """Stop preview, drop the feed, close hardware, and keep the logical active profile id."""
        await self.stop_preview()
        for unsub in self._preview_unsubs:
            unsub()
        self._preview_unsubs = []
        self.fov.clear_triggers()
        await self._hal.close()
        self._channels = {}

    async def set_active_profile(self, profile_id: str) -> str:
        """Select ``profile_id`` and drive hardware to it, keeping preview running across the switch."""
        async with self._lock:
            self._ensure_not_capturing()
            if profile_id == self._active_profile_id.value:
                return profile_id  # already active — avoid preview flicker and hardware churn
            was_previewing = self._mode.value == AcquisitionMode.PREVIEW
            if was_previewing:
                await self._stop_preview()
            try:
                await self._apply_profile(profile_id)
            finally:
                if was_previewing:
                    await self._start_preview()  # restored even on failure (on the rolled-back profile)
            return profile_id

    async def start_preview(self, channel_ids: Sequence[str] | None = None) -> None:
        """Start preview for the active profile."""
        async with self._lock:
            await self._start_preview(channel_ids)

    async def stop_preview(self) -> None:
        """Stop active preview if it is running."""
        async with self._lock:
            await self._stop_preview()

    async def _apply_profile(self, profile_id: str) -> None:
        """Drive hardware to a saved profile config. Pure: knows nothing about preview.

        The hardware steps read the active profile via the Cell, so the id is set first and rolled back
        on failure — it always names the last fully-applied profile. Requires exclusive access, guaranteed
        either by holding ``self._lock`` (the ``set_active_profile`` path) or by ``CAPTURE`` mode (the
        ``start_acquisition`` loop, where every other transition bails).
        """
        if profile_id not in self._bench.value.imaging.profiles:
            raise ProtocolError([f"no such profile '{profile_id}'"])
        previous_id = self._active_profile_id.value
        await self._active_profile_id.set(profile_id)
        try:
            # Invalidate preview before the colormap/viewport updates below: bump the epoch (clients clear
            # the previous profile's frames on the next status) and drop each camera's cached raw frame (so
            # the idle reprocess those updates trigger can't re-render the previous profile).
            await self._preview_epoch.set(self._preview_epoch.value + 1)
            await asyncio.gather(*(ch.camera.clear_preview_cache() for ch in self.active_channels.values()))
            await self._apply_filters()
            await self.apply_settings()
            for ch_id, ch in self.active_channels.items():
                ch.camera.preview_colormap.update(self._channel_config(ch_id).colormap)
            await self._run_setup_commands()
            await self._apply_ao()
            self.update_viewport()
        except Exception:
            await self._active_profile_id.set(previous_id)
            raise

    async def _start_preview(self, channel_ids: Sequence[str] | None = None) -> None:
        """Start preview for the active profile. Caller holds ``self._lock``."""
        if self._mode.value != AcquisitionMode.IDLE:
            logger.warning("Preview or Acquisition already running")
            return
        channels = self.active_channels
        all_chans = channels.values()
        chans = list(all_chans if channel_ids is None else [channels[ch] for ch in channel_ids if ch in channels])
        if not chans:
            raise ProtocolError(["no channels to preview"])
        self._preview_channels = chans

        results = await asyncio.gather(*(ch.start_preview() for ch in chans), return_exceptions=True)
        started = 0
        for ch, result in zip(chans, results, strict=True):
            if isinstance(result, BaseException):
                logger.error("Channel %s failed to start preview", ch.uid, exc_info=result)
            else:
                started += 1

        if started == 0:
            self._preview_channels = []
            raise RuntimeError("Preview failed to start on every channel")

        with suppress(NotImplementedError, RuntimeError):
            await self._hal.stage.scanning_axis.reset_ttl_stepper()

        await self._start_ao()
        await self._mode.set(AcquisitionMode.PREVIEW)
        logger.info("Preview started (%d cameras)", started)

    async def _stop_preview(self) -> None:
        """Stop active preview if it is running. Caller holds ``self._lock``.

        Safe to call in any mode: _preview_channels is non-empty only while previewing (start_preview
        bails unless IDLE; acquisition stops preview before entering CAPTURE), so this early-returns
        during a capture and never flips the mode out from under a running acquisition.
        """
        if not self._preview_channels:
            return
        chans, self._preview_channels = self._preview_channels, []

        results = await asyncio.gather(*(ch.stop_preview() for ch in chans), return_exceptions=True)
        for ch, result in zip(chans, results, strict=True):
            if isinstance(result, BaseException):
                logger.error("Channel %s failed to stop preview", ch.uid, exc_info=result)

        await self._stop_ao()
        await self._mode.set(AcquisitionMode.IDLE)
        logger.info("Preview stopped")

    async def apply_settings(self) -> None:
        """Apply saved rw props and camera ROIs for the active profile to hardware."""
        profile = self.active_profile
        if invalid := set(profile.props) - self._settable_devices():
            msg = f"devices not settable for profile '{self._active_profile_id.value}': {sorted(invalid)}"
            raise ProtocolError([msg])
        for device_id in sorted(profile.props):
            props = profile.props[device_id]
            if props and device_id in self._hal.devices:
                await self._hal.devices[device_id].props.set(**props)
        coros = []
        for ch_id, ch in self.active_channels.items():
            roi = profile.rois.get(self._channel_config(ch_id).detection)
            coros.append(ch.camera.update_roi(roi) if roi is not None else ch.camera.reset_roi())
        await asyncio.gather(*coros)
        await self.fov.get()

    async def save_settings(self) -> None:
        """Persist current rw props and camera ROIs into the active profile."""
        self._ensure_not_capturing()
        profile = self.active_profile
        settable = self._settable_devices()
        props = {**profile.props}
        rois = {**profile.rois}

        for device_id in sorted(settable):
            if device_id not in self._hal.devices:
                continue
            captured = await self._hal.devices[device_id].props.get_values("rw")
            captured.pop("roi", None)
            if captured:
                props[device_id] = captured
            if device_id in self._hal.cameras:
                camera = self._hal.cameras[device_id]
                roi = await camera.roi.get()
                sensor = camera.sensor_size_px.value
                if sensor is not None and roi.x == 0 and roi.y == 0 and roi.w == sensor.x and roi.h == sensor.y:
                    rois.pop(device_id, None)  # full sensor → store nothing; activate falls back to reset_roi
                else:
                    rois[device_id] = roi

        await self._update_active_profile_config(profile.model_copy(update={"props": props, "rois": rois}))

    async def save_as_default(self, include: Collection[str] = PROMOTABLE_FIELDS) -> None:
        """Persist the named baseline fields from the live bench into ``config.yaml``'s ``default``.

        ``include`` must be a subset of :data:`PROMOTABLE_FIELDS`; fields outside it keep their current
        on-disk baseline value. Defaults to every promotable field.
        """
        self._ensure_not_capturing()
        fields = set(include)
        if unknown := fields - PROMOTABLE_FIELDS:
            raise ProtocolError([f"cannot promote non-default fields: {sorted(unknown)}"])
        state = self._bench.value
        new_default = self._default.value.model_copy(update={f: getattr(state, f) for f in fields})
        save_yaml(self._path / "config.yaml", InstrumentConfig(hal=self._hal.config, default=new_default))
        await self._default.set(new_default)

    async def restore_default(self, include: Collection[str] = PROMOTABLE_FIELDS) -> None:
        """Reset the named baseline fields on the live bench to ``config.yaml``'s ``default``.

        ``include`` must be a subset of :data:`PROMOTABLE_FIELDS`. Run state (tasks, metadata) and any
        field outside ``include`` are left untouched. Defaults to every promotable field.
        """
        self._ensure_not_capturing()
        fields = set(include)
        if unknown := fields - PROMOTABLE_FIELDS:
            raise ProtocolError([f"cannot restore non-default fields: {sorted(unknown)}"])
        default = self._default.value
        await self._bench.update(**{f: getattr(default, f) for f in fields})

    async def update_ao_signals(self, ao_uid: str, signals: AOSignals) -> None:
        """Apply one AO signal config to hardware, then persist it into the active profile."""
        self._ensure_not_capturing()
        handle = self._hal.analog_outs.get(ao_uid)
        if handle is None:
            raise ProtocolError([f"AO device '{ao_uid}' not provisioned"])
        await handle.load(signals)
        await self._update_active_profile_config(
            self.active_profile.model_copy(update={"sync": {**self.active_profile.sync, ao_uid: signals}})
        )

    async def update_profile(self, patch: ProfilePatch) -> None:
        """Persist mutable fields on the active profile."""
        self._ensure_not_capturing()
        await self._update_active_profile_config(self.active_profile.model_copy(update=patch.changes()))

    async def update_channel(self, channel_id: str, patch: ChannelPatch) -> None:
        self._ensure_not_capturing()
        imaging = self._bench.value.imaging
        if channel_id not in imaging.channels:
            raise ProtocolError([f"no such channel '{channel_id}'"])
        changes = patch.changes()
        updated = imaging.channels[channel_id].model_copy(update=changes)
        imaging = imaging.model_copy(update={"channels": {**imaging.channels, channel_id: updated}})
        await self._bench.update(imaging=imaging)
        if "emission" in changes and channel_id in self.active_channels:
            self.active_channels[channel_id].camera.preview_colormap.update(updated.colormap)

    async def update_output(self, patch: WriterPatch) -> None:
        self._ensure_not_capturing()
        output = self._bench.value.output.model_copy(update=patch.changes())
        await self._bench.update(output=output)

    async def update_stencil(self, patch: StencilPatch) -> None:
        self._ensure_not_capturing()
        stencil = self._bench.value.stencil.model_copy(update=patch.changes())
        await self._bench.update(stencil=stencil)

    async def update_metadata(self, **fields: Any) -> None:
        """Merge ``fields`` into the experiment metadata, validated against the active metadata schema.

        ``metadata_cls`` is the (dynamic, per-instrument) schema, so the merged dict is validated against
        it rather than a static ``Patch`` model: unknown keys and bad values are rejected as a
        :class:`ProtocolError`.
        """
        self._ensure_not_capturing()
        state = self._bench.value
        merged = {**state.metadata, **fields}
        try:
            validated = state.metadata_cls.model_validate(merged).model_dump()
        except ValidationError as e:
            raise ProtocolError([err["msg"] for err in e.errors()]) from e
        await self._bench.update(metadata=validated)

    async def set_metadata_schema(self, schema: type[ExperimentMetadata] | str) -> None:
        """Switch the metadata schema (``metadata_cls``), re-seeding ``metadata`` to the new schema.

        Best-effort carryover: values for fields the new schema still defines (e.g. ``notes`` across
        base↔subclass) are kept; if they don't validate, ``metadata`` falls back to the new schema's
        defaults so the switch always succeeds.
        """
        self._ensure_not_capturing()
        cls = resolve_metadata_class(schema) if isinstance(schema, str) else schema
        carried = {k: v for k, v in self._bench.value.metadata.items() if k in cls.model_fields}
        try:
            metadata = cls.model_validate(carried).model_dump()
        except ValidationError:
            metadata = cls().model_dump()
        await self._bench.update(metadata_cls=cls, metadata=metadata)

    async def set_traversal(self, order: TileOrder) -> None:
        self._ensure_not_capturing()
        await self._bench.update(traversal=order)

    async def add_tasks(self, xy: Sequence[tuple[float, float]], *, profile_ids: Sequence[str] | None = None) -> None:
        """Add a task at each (x, y), defaulting to the active profile."""
        self._ensure_not_capturing()
        state = self._bench.value
        profiles = list(profile_ids) if profile_ids is not None else [self._active_profile_id.value]
        if not profiles:
            raise ProtocolError(["add_tasks requires at least one profile id"])
        tasks = {
            uuid.uuid4().hex: AcquisitionTask(
                x=x, y=y, start=state.stencil.z_start, end=state.stencil.z_end, profile_ids=profiles
            )
            for x, y in xy
        }
        await self._bench.update(tasks={**state.tasks, **tasks})

    async def remove_tasks(self, task_ids: Sequence[str]) -> None:
        """Delete one or more tasks in a single bench update."""
        self._ensure_not_capturing()
        tasks = self._bench.value.tasks
        if unknown := [tid for tid in task_ids if tid not in tasks]:
            raise ProtocolError([f"no such task '{tid}'" for tid in unknown])
        remove = set(task_ids)
        await self._bench.update(tasks={tid: t for tid, t in tasks.items() if tid not in remove})

    async def update_tasks(self, patches: Mapping[str, TaskPatch]) -> None:
        """Apply a per-task patch to one or more tasks in a single bench update."""
        self._ensure_not_capturing()
        tasks = self._bench.value.tasks
        if unknown := [tid for tid in patches if tid not in tasks]:
            raise ProtocolError([f"no such task '{tid}'" for tid in unknown])
        updated = {
            tid: (t.model_copy(update=patches[tid].changes()) if tid in patches else t) for tid, t in tasks.items()
        }
        await self._bench.update(tasks=updated)

    async def start_acquisition(self, request: AcquisitionRequest) -> AcquisitionRecord:
        """Begin acquiring the requested volumes into ``request.storage``; return the record once started.

        ``storage`` is the run's logical destination (root + relative base; the node resolves it).
        ``task_ids`` selects a subset of planned tasks (``None`` → all), always captured in traversal
        order. Runs the preflight (each participating camera must be able to write ``storage``) and writes
        ``<run>/record.json`` (a snapshot of the plan + hardware) **synchronously** — so a bad target or
        an empty/unknown selection fails here — then launches the capture loop in the background and
        returns the record. The run streams :attr:`progress` and ends by returning :attr:`mode` to
        ``IDLE``; stop it early with :meth:`stop_acquisition`, or await it with :meth:`wait_acquisition`.
        """
        storage = request.storage
        state = self._bench.value
        plan = self._generate_plan(request.task_ids)
        if not plan:
            raise RuntimeError("No tasks planned — add tasks before acquiring")
        # Hold the lock only for the entry transition (reject-if-capturing → stop preview → enter CAPTURE),
        # not the whole run: that keeps a second start_acquisition a fast reject rather than a queued re-run.
        # The run itself is exclusive because CAPTURE makes every other transition method bail.
        async with self._lock:
            if self._mode.value == AcquisitionMode.CAPTURE:
                raise RuntimeError("An acquisition is already in progress")
            if self._mode.value == AcquisitionMode.PREVIEW:
                await self._stop_preview()
            await self._mode.set(AcquisitionMode.CAPTURE)
        try:
            # Preflight: every camera in the plan must be able to write `storage`, tested on its own node
            # (round-trip write). Any failure raises here — before record.json, motion, or capture.
            detections = {
                state.imaging.channels[ch_id].detection
                for v in plan
                for ch_id in state.imaging.profiles[v.profile].channels
                if ch_id in state.imaging.channels
            }
            cameras = [self._hal.cameras[d] for d in detections if d in self._hal.cameras]
            await asyncio.gather(*(cam.check_writable(storage) for cam in cameras))

            record = AcquisitionRecord(
                record_id=storage.path.name,
                origin=Origin(on=System.hostname(), by=request.operator or getpass.getuser()),
                volumes=plan,
                state=state,
                hardware=self._hal.config,
            )
            run_root = storage.resolve().target
            run_root.mkdir(parents=True, exist_ok=True)
            (run_root / "record.json").write_text(record.model_dump_json(indent=2))
        except BaseException:
            await self._mode.set(AcquisitionMode.IDLE)  # preflight/record failed — release CAPTURE
            raise

        self._acq_task = asyncio.create_task(self._run_acquisition(storage, plan))
        return record

    async def stop_acquisition(self) -> None:
        """Cancel the in-flight acquisition, if any; its cleanup runs and ``mode`` returns to IDLE."""
        if (task := self._acq_task) is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def wait_acquisition(self) -> None:
        """Await the in-flight acquisition's completion (no-op if none is running)."""
        if (task := self._acq_task) is not None:
            with suppress(asyncio.CancelledError):
                await task

    async def _run_acquisition(self, storage: StorageSpec, plan: list[PlannedVolume]) -> None:
        """Capture each planned (task, profile) volume in order. Runs as the background ``_acq_task``.

        Reads the bench live — it's frozen for the whole run (CAPTURE blocks edits) — and delegates each
        volume to :meth:`_capture_volume`. A volume failure **aborts the run** (remaining volumes are
        skipped) and is logged here, so the failure is observed even though the run is fire-and-launched;
        cancellation (via :meth:`stop_acquisition`) propagates normally. ``mode`` returns to IDLE when the
        run ends, completes, fails, or is cancelled.
        """
        tasks = self._bench.value.tasks
        try:
            for v in plan:
                await self._apply_profile(v.profile)
                subpath = PurePosixPath(tasks[v.task].signature, v.profile)
                await self._capture_volume(tasks[v.task].stack, storage, subpath, task=v.task, profile=v.profile)
            logger.info("Acquisition complete: %d volumes → %s", len(plan), storage.resolve().target)
        except Exception:
            logger.exception("Acquisition aborted")
        finally:
            self._acq_task = None
            # Free each camera's writer ring (workers + ~hundreds of GB shared memory) now the run is
            # over — it's kept resident across volumes for reuse, but not indefinitely afterward. The
            # next acquisition re-allocates it cold. Runs on completion, failure, or cancellation.
            released = await asyncio.gather(
                *(cam.release_writer() for cam in self._hal.cameras.values()), return_exceptions=True
            )
            for cam_id, result in zip(self._hal.cameras, released, strict=True):
                if isinstance(result, BaseException):
                    logger.warning("release_writer failed for %s: %r", cam_id, result)
            await self._mode.set(AcquisitionMode.IDLE)

    async def _capture_volume(
        self,
        stack: ZStack,
        storage: StorageSpec,
        subpath: PurePosixPath,
        *,
        task: str,
        profile: str,
    ) -> None:
        """Acquire one volume for the already-active profile, emitting :attr:`progress` per batch.

        The ``finally`` disables lasers, resets the stepper, and finalizes the writers — so a cancel
        leaves hardware safe and the partial stack finalized.
        """
        settings = self._bench.value.output
        channels = self.active_channels
        scanning_axis = self._hal.stage.scanning_axis
        z_step = self.active_profile.z_step
        num_frames = stack.num_frames(z_step)
        batch_z = settings.batch_z
        progress = AcquisitionProgress(task=task, profile=profile, done=0, total=num_frames)
        await self.progress.emit(progress)
        try:
            await asyncio.gather(
                self._hal.stage.x.move_abs(stack.x, wait=True),
                self._hal.stage.y.move_abs(stack.y, wait=True),
                self._hal.stage.z.move_abs(stack.start, wait=True),
            )
            await scanning_axis.configure_ttl_stepper(TTLStepperConfig(step_mode=StepMode.RELATIVE))
            init_coros = []
            for ch_id, ch in channels.items():
                config = self._channel_config(ch_id)
                init_coros.append(
                    ch.camera.open_stack(
                        storage=storage,
                        subpath=subpath / ch_id,
                        num_frames=num_frames,
                        z_step=z_step,
                        magnification=self._hal.config.detection[config.detection].magnification,
                        settings=settings,
                    )
                )
            refs = await asyncio.gather(*init_coros)

            profile_root = storage.resolve(subpath).target
            profile_root.mkdir(parents=True, exist_ok=True)
            for ch_id, ref in zip(channels, refs, strict=True):
                (profile_root / f"{ch_id}.ref.json").write_text(ref.model_dump_json(indent=2))

            await asyncio.gather(*(ch.enable_laser() for ch in channels.values()))

            for batch_idx in range(math.ceil(num_frames / batch_z)):
                frames_in_batch = min(batch_z, num_frames - batch_idx * batch_z)
                for _ in range(frames_in_batch):
                    await scanning_axis.queue_relative_move(z_step)
                # begin_batch waits for a free writer slot and arms the camera before returning,
                # so the AO is safe to fire once these resolve.
                await asyncio.gather(*(ch.camera.begin_batch(frames_in_batch) for ch in channels.values()))
                await self._start_ao()
                while True:
                    states = await asyncio.gather(*(ch.camera.capture_state() for ch in channels.values()))
                    if all(state is CaptureState.DONE for state in states):
                        break
                    await asyncio.sleep(0.05)
                await self._stop_ao()
                done = min((batch_idx + 1) * batch_z, num_frames)
                await self.progress.emit(progress.updated(done=done))
        finally:
            await self._teardown_capture(list(channels.values()), scanning_axis)
        logger.info("Captured %d frames: task %s / profile %s", num_frames, task, profile)

    async def _teardown_capture(self, chans: list[Channel], scanning_axis: ContinuousAxisHandle) -> None:
        """Cleanup after a volume, regardless of how capture exited: disable lasers, reset the stepper,
        then drain and close every writer. Per-camera failures are logged, never raised, so one bad
        camera can't block the others' cleanup.

        Close runs in the background on each node; this polls ``capture_state`` until every camera
        reports ``CLOSED``. Each poll is a short RPC, so a hung/dead node surfaces via its timeout
        rather than blocking cleanup indefinitely.
        """

        def _report(label: str, results: list[Any]) -> None:
            for ch, result in zip(chans, results, strict=True):
                if isinstance(result, BaseException):
                    logger.error("cleanup: %s failed for %s", label, ch.uid, exc_info=result)

        _report("disable_laser", await asyncio.gather(*(ch.disable_laser() for ch in chans), return_exceptions=True))
        with suppress(NotImplementedError, RuntimeError):
            await scanning_axis.reset_ttl_stepper()
        _report("close_stack", await asyncio.gather(*(ch.camera.close_stack() for ch in chans), return_exceptions=True))
        pending = list(chans)
        while pending:
            states = await asyncio.gather(*(ch.camera.capture_state() for ch in pending), return_exceptions=True)
            still_closing = []
            for ch, state in zip(pending, states, strict=True):
                if isinstance(state, BaseException):
                    logger.error("cleanup: close_stack failed for %s", ch.uid, exc_info=state)
                elif state is not CaptureState.CLOSED:
                    still_closing.append(ch)
            pending = still_closing
            if pending:
                await asyncio.sleep(0.05)

    async def _update_active_profile_config(self, profile: ProfileConfig) -> None:
        imaging = self._bench.value.imaging
        profile_id = self._active_profile_id.value
        imaging = imaging.model_copy(update={"profiles": {**imaging.profiles, profile_id: profile}})
        await self._bench.update(imaging=imaging)

    async def _subscribe_camera(self, cam_id: str, camera: CameraHandle) -> None:
        async def forward_frames(data: bytes) -> None:
            if (channel_id := self._channel_for_camera(cam_id)) is not None:
                await self.frames.emit((channel_id, data))

        async def forward_views(data: bytes) -> None:
            if (channel_id := self._channel_for_camera(cam_id)) is not None:
                await self.views.emit((channel_id, data))

        self._preview_unsubs.append(camera.subscribe("preview", forward_frames))
        self._preview_unsubs.append(camera.subscribe("preview_view", forward_views))

    async def _apply_filters(self) -> None:
        desired: dict[str, str] = {}
        for ch_id in self.active_channels:
            desired.update(self._channel_config(ch_id).filters)
        coros = []
        for fw_id, slot in desired.items():
            if (fw := self._hal.fws.get(fw_id)) is not None:
                coros.append(fw.call("select", slot, wait=True))
        await asyncio.gather(*coros)

    async def _apply_ao(self) -> None:
        for uid, signals in self.active_profile.sync.items():
            handle = self._hal.analog_outs.get(uid)
            if handle is None:
                logger.warning(
                    "Profile '%s' references AO '%s' which is not provisioned", self._active_profile_id.value, uid
                )
                continue
            await handle.load(signals)

    async def _start_ao(self) -> None:
        handles = [self._hal.analog_outs[uid] for uid in self.active_profile.sync if uid in self._hal.analog_outs]
        await asyncio.gather(*(h.start() for h in handles))

    async def _stop_ao(self) -> None:
        handles = [self._hal.analog_outs[uid] for uid in self.active_profile.sync if uid in self._hal.analog_outs]
        await asyncio.gather(*(h.stop() for h in handles))

    async def _run_setup_commands(self) -> None:
        for device_id, commands in self.active_profile.setup.items():
            handle = self._hal.devices.get(device_id)
            if handle is None:
                logger.warning("setup: device '%s' not found, skipping", device_id)
                continue
            result = await handle.run_commands(commands)
            if not result.is_ok:
                logger.warning("Some setup commands failed for '%s'", device_id)

    async def _compute_current_fov(self) -> tuple[float, float]:
        if not self._hal.cameras:
            raise RuntimeError("Instrument is not open")
        detection = self._hal.config.detection
        fovs: list[tuple[float, float]] = []
        for ch_id, channel in self.active_channels.items():
            frame_area = await channel.camera.frame_area_um.get()
            path = detection[self._channel_config(ch_id).detection]
            w, h = frame_area.x / path.magnification, frame_area.y / path.magnification
            if path.rotation_deg % 180 != 0:
                w, h = h, w
            fovs.append((w, h))
        active_id = self._active_profile_id.value
        if fovs:
            if not all(f == fovs[0] for f in fovs):
                logger.warning("Profile '%s' cameras disagree on FOV; using bounding box", active_id)
            return (max(w for w, _ in fovs), max(h for _, h in fovs))

        return self._bench.value.imaging.compute_saved_fov([active_id], self._hal)

    def _generate_plan(self, task_ids: list[str] | None) -> list[PlannedVolume]:
        """Resolve the ordered (task, profile) volumes to capture; validate an explicit selection.

        ``task_ids`` is a selection, not an ordering: order always comes from the traversal query, so a
        subset is visited in the same spatial order as the full run. Unknown ids raise ``ProtocolError``.
        """
        tasks = self._bench.value.tasks
        if task_ids is not None and (unknown := [t for t in task_ids if t not in tasks]):
            raise ProtocolError([f"no such task '{t}'" for t in unknown])
        selected = None if task_ids is None else set(task_ids)
        return [
            PlannedVolume(task=tile.task_id, profile=pid)
            for tile in self.task_tiles.value
            if selected is None or tile.task_id in selected
            for pid in tasks[tile.task_id].profile_ids
        ]

    def _ensure_not_capturing(self) -> None:
        if self._mode.value == AcquisitionMode.CAPTURE:
            raise RuntimeError("Cannot mutate instrument state while acquisition is running")

    def _settable_devices(self) -> set[str]:
        return self._bench.value.imaging.get_profile_settable_devices(self._active_profile_id.value, self._hal.config)

    def _channel_config(self, channel_id: str) -> ChannelConfig:
        return self._bench.value.imaging.channels[channel_id]

    def _channel_for_camera(self, camera_id: str) -> str | None:
        for ch_id in self.active_profile.channels:
            config = self._bench.value.imaging.channels.get(ch_id)
            if config is not None and config.detection == camera_id and ch_id in self._channels:
                return ch_id
        return None

    def _build_channels(self) -> dict[str, Channel]:
        if not self._hal.devices:
            return {}
        channels: dict[str, Channel] = {}
        for uid, config in self._bench.value.imaging.channels.items():
            camera = self._hal.cameras.get(config.detection)
            if camera is None:
                raise ValueError(f"Channel '{uid}' references detection path '{config.detection}' with no camera")
            laser = self._hal.lasers.get(config.illumination)
            if laser is None:
                raise ValueError(f"Channel '{uid}' references illumination '{config.illumination}' with no laser")
            channels[uid] = Channel(uid=uid, camera=camera, laser=laser)
        return channels

    def _compute_task_tiles(self) -> list[TaskTile]:
        """Each task's footprint tile (position + its profiles' combined FOV), in traversal order.

        Replaces the old (tiles-dict + order-list) pair. The traversal is generic over the ``Tile``
        subtype, so it returns the :class:`TaskTile`s — each carrying its ``task_id`` — already ordered.
        Read the order with ``[tt.task_id for tt in task_tiles.value]``.
        """
        state = self._bench.value
        tiles: list[TaskTile] = []
        for key, task in state.tasks.items():
            w, h = state.imaging.compute_saved_fov(task.profile_ids, self._hal)
            tiles.append(TaskTile(task_id=key, x=task.x, y=task.y, w=w, h=h))
        return list(state.traversal(tiles))
