import datetime
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self

from ome_zarr_writer import Compression, DownscaleType, ScaleLevel, WriterSettings
from pydantic import Field, ValidationInfo, field_validator, model_validator
from vxlib.schema import FrozenModel

from rigup import CommandRequest
from vxl._utils.color import Color
from vxl.devices.camera import SensorROI
from vxl.devices.daq.clocked import Signals
from vxl.hal import DiscreteAxisPositions, HardwareTopology

from .errors import Violation, ViolationLoc, assignment_violations
from .metadata import ExperimentMetadata, MetadataCls
from .traversal import TileOrder


class Patch(FrozenModel):
    """Base for partial-update models: only the fields the caller explicitly set are applied.

    ``extra="forbid"`` rejects unknown keys at construction, so a typo'd field fails loudly at the
    boundary instead of being silently dropped. :meth:`changes` returns exactly the set fields
    (including any explicitly set to ``None``, so a nullable field can be cleared).
    """

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class ChannelConfig(FrozenModel):
    detection: str
    illumination: str
    filters: DiscreteAxisPositions = Field(default_factory=dict)
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


class ProfileConfig(FrozenModel):
    """A named microscope profile: active channels and clocked signal configurations.

    ``sync`` is keyed by signal-generator UID. A profile may drive any subset of
    the generators present in the rig.
    """

    channels: list[str] = Field(min_length=1)
    z_step: float = Field(..., gt=0, description="Axial step between frames in µm (one scan-axis move per frame)")
    sync: dict[str, Signals] = Field(default_factory=dict)
    props: dict[str, dict[str, Any]] = Field(default_factory=dict)
    setup: dict[str, list[CommandRequest]] = Field(default_factory=dict)
    rois: dict[str, SensorROI] = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None


class ProfilePatch(Patch):
    z_step: Annotated[float, Field(gt=0)] | None = None
    desc: str | None = None
    label: str | None = None


class FixedOpticalRoutingPolicy(FrozenModel):
    type: Literal["fixed"]
    route: str


class SplitOpticalRoutingPolicy(FrozenModel):
    type: Literal["split"]
    axis: Literal["x", "y"]
    threshold: float = Field(allow_inf_nan=False)
    lower: str
    upper: str

    @model_validator(mode="after")
    def validate_distinct_routes(self) -> Self:
        if self.lower == self.upper:
            raise ValueError("Split optical-routing policies must use different lower and upper routes")
        return self

    def resolve(self, coordinate: float, *, previous: str | None = None, margin: float = 0) -> str:
        """Resolve one side, retaining ``previous`` within the symmetric hysteresis margin."""
        if margin < 0:
            raise ValueError("margin must be non-negative")
        if previous == self.lower:
            return self.upper if coordinate >= self.threshold + margin else self.lower
        if previous == self.upper:
            return self.lower if coordinate < self.threshold - margin else self.upper
        return self.lower if coordinate < self.threshold else self.upper


type OpticalRoutingPolicy = Annotated[
    FixedOpticalRoutingPolicy | SplitOpticalRoutingPolicy,
    Field(discriminator="type"),
]


class ImagingProtocol(FrozenModel):
    channels: dict[str, ChannelConfig]
    profiles: dict[str, ProfileConfig]

    @field_validator("channels", "profiles")
    @classmethod
    def at_least_one[M: ChannelConfig | ProfileConfig](cls, v: dict[str, M], info: ValidationInfo) -> dict[str, M]:
        if not v:
            raise ValueError(f"at least one {(info.field_name or 'entry').rstrip('s')} must be present")
        return v

    def get_profile_settable_devices(self, profile_id: str, hal: HardwareTopology) -> set[str]:
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
        for signals in profile.sync.values():
            ids.update(signals.waveforms.keys())
        return ids - hal.filter_wheels

    def hal_violations(self, hal: HardwareTopology, *, loc: ViolationLoc) -> list[Violation]:
        """Return relationships between this imaging protocol and a HAL config that cannot resolve."""
        violations = []
        for ch_id, ch in self.channels.items():
            detection = hal.detection.get(ch.detection)
            if detection is None:
                violations.append(
                    Violation(
                        code="imaging.channel.detection_missing",
                        msg=f"Detection assembly '{ch.detection}' is not configured.",
                        loc=(*loc, "channels", ch_id, "detection"),
                    )
                )
            else:
                violations.extend(
                    assignment_violations(
                        expected=detection.filter_wheels,
                        assigned=ch.filters,
                        loc=(*loc, "channels", ch_id, "filters"),
                        code="imaging.channel.filter",
                        label="filter-wheel",
                    )
                )
                expected_filters = set(detection.filter_wheels)
                violations.extend(
                    hal.check_discrete_axis_positions(
                        {uid: position for uid, position in ch.filters.items() if uid in expected_filters},
                        loc=(*loc, "channels", ch_id, "filters"),
                    )
                )

            if ch.illumination not in hal.illumination:
                violations.append(
                    Violation(
                        code="imaging.channel.illumination_missing",
                        msg=f"Illumination assembly '{ch.illumination}' is not configured.",
                        loc=(*loc, "channels", ch_id, "illumination"),
                    )
                )

        for profile_id, profile in self.profiles.items():
            for generator_uid in profile.sync:
                if generator_uid not in hal.device_uids:
                    violations.append(
                        Violation(
                            code="imaging.profile.sync_device_missing",
                            msg=f"Signal generator '{generator_uid}' is not configured.",
                            loc=(*loc, "profiles", profile_id, "sync", generator_uid),
                        )
                    )

            settable = self.get_profile_settable_devices(profile_id, hal)
            # setup runs arbitrary device commands (not props), so it may legitimately target filter
            # wheels — which are intentionally excluded from `settable` (props drive them via select).
            setup_targets = settable | hal.filter_wheels

            for device_id in profile.props:
                if device_id not in settable:
                    violations.append(
                        Violation(
                            code="imaging.profile.props_inactive",
                            msg=f"Device '{device_id}' is not active in this profile.",
                            loc=(*loc, "profiles", profile_id, "props", device_id),
                        )
                    )

            for device_id in profile.setup:
                if device_id not in setup_targets:
                    violations.append(
                        Violation(
                            code="imaging.profile.setup_inactive",
                            msg=f"Device '{device_id}' is not active in this profile.",
                            loc=(*loc, "profiles", profile_id, "setup", device_id),
                        )
                    )

        return violations

    def logical_violations(self, *, loc: ViolationLoc) -> list[Violation]:
        """Return relationships within the imaging protocol that cannot be satisfied."""
        violations = []
        for profile_id, profile in self.profiles.items():
            profile_loc = (*loc, "profiles", profile_id)
            duplicates = sorted({ch for ch in profile.channels if profile.channels.count(ch) > 1})
            if duplicates:
                violations.append(
                    Violation(
                        code="imaging.profile.channels_duplicate",
                        msg=f"Channels must be unique (duplicates: {duplicates}).",
                        loc=(*profile_loc, "channels"),
                    )
                )

            valid_channel_ids = []
            for index, ch_id in enumerate(profile.channels):
                if ch_id in self.channels:
                    if ch_id not in valid_channel_ids:
                        valid_channel_ids.append(ch_id)
                else:
                    violations.append(
                        Violation(
                            code="imaging.profile.channel_missing",
                            msg=f"Channel '{ch_id}' is not defined in the imaging protocol.",
                            loc=(*profile_loc, "channels", index),
                        )
                    )
            if valid_channel_ids:
                detection_channels: dict[str, str] = {}
                filter_positions: dict[str, dict[str, list[str]]] = {}
                for ch_id in valid_channel_ids:
                    channel = self.channels[ch_id]
                    if channel.detection in detection_channels:
                        first_channel = detection_channels[channel.detection]
                        violations.append(
                            Violation(
                                code="imaging.profile.detection_conflict",
                                msg=(
                                    f"Channels '{first_channel}' and '{ch_id}' both use detection "
                                    f"assembly '{channel.detection}'."
                                ),
                                loc=(*profile_loc, "channels"),
                            )
                        )
                    else:
                        detection_channels[channel.detection] = ch_id
                    for fw_id, filter_label in channel.filters.items():
                        filter_positions.setdefault(fw_id, {}).setdefault(filter_label, []).append(ch_id)

                for fw_id, positions in filter_positions.items():
                    if len(positions) > 1:
                        details = ", ".join(f"'{label}' by {channels}" for label, channels in positions.items())
                        violations.append(
                            Violation(
                                code="imaging.profile.filter_conflict",
                                msg=f"Filter '{fw_id}' is assigned conflicting positions: {details}.",
                                loc=(*profile_loc, "channels"),
                            )
                        )

                active_cameras = {self.channels[ch_id].detection for ch_id in valid_channel_ids}
                for roi_device_id in profile.rois:
                    if roi_device_id not in active_cameras:
                        violations.append(
                            Violation(
                                code="imaging.profile.roi_inactive",
                                msg=f"No active channel uses camera '{roi_device_id}'.",
                                loc=(*profile_loc, "rois", roi_device_id),
                            )
                        )

        return violations


class Stencil(FrozenModel):
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


class ZStack(FrozenModel):
    """A stage position and z-range. All coordinates are absolute stage positions in micrometers (µm)."""

    x: float
    y: float
    start: float
    end: float

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.end < self.start:
            raise ValueError(f"z-range end ({self.end}) must be >= start ({self.start})")
        return self

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


class InstrumentDefaults(FrozenModel):  # everything that can live in config.default
    imaging: ImagingProtocol
    routing: dict[str, OpticalRoutingPolicy] = Field(default_factory=dict)
    metadata_cls: MetadataCls = ExperimentMetadata
    output: WriterSettings = Field(default_factory=WriterSettings)
    stencil: Stencil = Field(default_factory=Stencil)
    traversal: TileOrder = TileOrder.SNAKE_ROW

    def resolve_routes(
        self,
        *,
        x: float,
        y: float,
        previous: Mapping[str, str] | None = None,
        margins: Mapping[str, float] | None = None,
    ) -> dict[str, str]:
        """Resolve every optical-routing policy for an XY position."""
        coordinates = {"x": x, "y": y}
        previous = previous or {}
        margins = margins or {}
        routes = {}
        for dimension, policy in self.routing.items():
            match policy:
                case FixedOpticalRoutingPolicy(route=route):
                    routes[dimension] = route
                case SplitOpticalRoutingPolicy(axis=axis):
                    routes[dimension] = policy.resolve(
                        coordinates[axis],
                        previous=previous.get(dimension),
                        margin=margins.get(axis, 0),
                    )
        return routes

    def semantic_violations(self, hal: HardwareTopology, *, loc: ViolationLoc) -> list[Violation]:
        """Return all cross-section violations in these defaults."""
        imaging_loc = (*loc, "imaging")
        return [
            *self.imaging.logical_violations(loc=imaging_loc),
            *self.imaging.hal_violations(hal, loc=imaging_loc),
            *self._routing_violations(hal, loc=(*loc, "routing")),
        ]

    def _routing_violations(self, hal: HardwareTopology, *, loc: ViolationLoc) -> list[Violation]:
        participating: set[str] = set()
        for assemblies in (hal.detection, hal.illumination):
            for assembly in assemblies.values():
                for dimension in assembly.routing:
                    if dimension in hal.optical_routing.root:
                        participating.add(dimension)

        violations = assignment_violations(
            expected=participating,
            assigned=self.routing,
            loc=loc,
            code="optical_routing.policy",
            label="routing-policy",
        )
        for dimension, policy in self.routing.items():
            routes = hal.optical_routing.root.get(dimension)
            if routes is None or dimension not in participating:
                continue

            selected: list[tuple[str, str]]
            match policy:
                case FixedOpticalRoutingPolicy(route=route):
                    selected = [("route", route)]
                case SplitOpticalRoutingPolicy(lower=lower, upper=upper):
                    selected = [("lower", lower), ("upper", upper)]

            for field, route in selected:
                if route not in routes:
                    violations.append(
                        Violation(
                            code="optical_routing.policy.route_missing",
                            msg=f"Route '{route}' is not defined for routing dimension '{dimension}'.",
                            loc=(*loc, dimension, field),
                        )
                    )
        return violations


class InstrumentPreset(InstrumentDefaults):
    """Reusable instrument configuration and acquisition tasks, excluding specimen metadata."""

    tasks: dict[str, AcquisitionTask] = Field(default_factory=dict)

    @classmethod
    def from_state(cls, state: "InstrumentState") -> Self:
        """Extract the reusable preset fields from complete instrument state."""
        return cls.model_validate(state.model_dump(include=set(cls.model_fields)))

    def semantic_violations(self, hal: HardwareTopology, *, loc: ViolationLoc = ("state",)) -> list[Violation]:
        """Return all cross-section violations in the reusable preset."""
        violations = super().semantic_violations(hal, loc=loc)
        for task_id, task in self.tasks.items():
            for index, profile_id in enumerate(task.profile_ids):
                if profile_id not in self.imaging.profiles:
                    violations.append(
                        Violation(
                            code="task.profile_missing",
                            msg=f"Profile '{profile_id}' is not defined in the imaging protocol.",
                            loc=(*loc, "tasks", task_id, "profile_ids", index),
                        )
                    )
        return violations


class InstrumentState(InstrumentPreset):
    """Persisted operator-editable state: a preset plus specimen metadata and modification time."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    last_modified: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.UTC))


class InstrumentConfig(FrozenModel):
    """A complete instrument spec: the :class:`HardwareTopology` plus a baseline
    acquisition state (``default``). Shared by shipped ``.voxel.yaml`` templates and each instrument's
    on-disk ``config.yaml`` — a template is just a config without a ``.voxel`` home yet."""

    hal: HardwareTopology
    default: InstrumentDefaults

    def semantic_violations(self) -> list[Violation]:
        """Return all statically knowable relationships that conflict within the config."""
        return [
            *self.hal.semantic_violations(loc=("config", "hal")),
            *self.default.semantic_violations(self.hal, loc=("config", "default")),
        ]
