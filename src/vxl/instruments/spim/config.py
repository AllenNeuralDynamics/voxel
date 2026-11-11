"""The files of a SPIM instrument: ``config.yaml``, its defaults, ``state.json`` and presets."""

from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import Field, PositiveFloat, field_validator, model_validator
from rigup.config import DeviceUid
from rigup.device.schema import CommandRequest
from vxlib.schema import FrozenModel, UniqueList, identifier, repeated
from vxlib.units import Portion
from vxlib.vector import Vec2D, Vec3D

from vxl.core.config import InstrumentConfig, InstrumentState, InstrumentTemplate, NotDefault
from vxl.hal_next.config import (
    DigitalWire,
    LightPath,
    SpecimenAxis,
    Stage,
    Wire,
)
from vxl.hal_next.config import HALConfig as BaseHALConfig
from vxl.hal_next.errors import Violation, assignment_violations, not_configured, under
from vxl.hal_next.signals import Timeline
from vxl.models import AreaROI, AxisPosition

ProfileId = Annotated[str, identifier("Profile id")]
TaskId = Annotated[str, identifier("Task id")]

SOFTWARE = "software"
"""The pacer of a capture that the program runs frame by frame."""

type Motion = Literal["step", "sweep"]
"""``step``: move, stop, take the frame. ``sweep``: take frames while moving."""


class Scan(FrozenModel):
    """How 1 capture runs. ``axis`` is the stage axis that it moves; the other 2 are tiled. ``pacer`` is the device
    whose own clock or pulses set the rhythm, or ``software``. ``margin`` is how much slower a sweep runs than
    spacing ÷ frame time, so that no pulse of the stage comes before a frame ends."""

    axis: SpecimenAxis
    motion: Motion
    pacer: DeviceUid | Literal["software"]
    margin: Portion | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.motion == "step" and self.margin is not None:
            raise ValueError("'margin' is for a sweep; a step has none")
        if self.motion == "sweep" and self.pacer == SOFTWARE:
            raise ValueError("the program can pace a step, not a sweep")
        return self

    def tiled(self) -> list[SpecimenAxis]:
        """The stage axes that a capture does not move."""
        return [axis for axis in Stage.axes() if axis != self.axis]


@dataclass(frozen=True)
class Chain:
    """What starts each device in 1 capture. ``starters`` start by themselves: the pacer, or every generator when the
    program paces. ``waits`` gives the wire whose pulses start each other device. ``unstarted`` lists each camera,
    generator or stepping axis that nothing starts."""

    starters: tuple[DeviceUid, ...]
    waits: Mapping[DeviceUid, Wire]
    unstarted: tuple[DeviceUid, ...]


class HALConfig(BaseHALConfig, frozen=True):
    """The bench of a SPIM instrument: ``scan`` adds how 1 capture runs."""

    scan: Scan

    def violations(self) -> list[Violation]:
        return [
            *super().violations(),
            *self._software_violations(),
            *under(("scan",), self._scan_violations()),
        ]

    def _software_violations(self) -> list[Violation]:
        if SOFTWARE not in self.device_uids:
            return []
        return [
            Violation(
                code="hal.reserved_name",
                msg="'software' names the program as the pacer of a scan, so no device takes it.",
                loc=("devices", SOFTWARE),
            )
        ]

    def _scan_violations(self) -> list[Violation]:
        pacer = self.scan.pacer
        if pacer != SOFTWARE and pacer not in self.device_uids:
            return [not_configured("Device", pacer, code="hal.scan.pacer_missing", loc=("pacer",))]
        return [
            Violation(
                code="hal.scan.unstarted",
                msg=f"Nothing starts '{device}': no wire in the chain from the pacer reaches it.",
                loc=("pacer",),
            )
            for device in self.chain().unstarted
        ]

    def chain(self) -> Chain:
        """What starts each device in 1 capture, worked out from ``scan`` and the wires. Follow the digital wires from
        the pacer. Each camera, generator, or axis that steps waits on the first wire that reaches it. A starter never
        waits, an axis that sweeps never waits, and with ``software`` the program moves the axis. A wire to any other
        device, such as a laser's gate, starts nothing."""
        by_program = self.scan.pacer == SOFTWARE
        generators = self.generators()
        waiting = {*self.optics.detectors(), *generators}
        if self.scan.motion == "step" and not by_program:
            waiting.add(self.stage.device(self.scan.axis))
        starters = tuple(sorted(generators)) if by_program else (self.scan.pacer,)

        waits: dict[DeviceUid, Wire] = {}
        reached, pending = set(starters), list(starters)
        while pending:
            sender = pending.pop(0)
            for name, config in self.wiring.outputs(sender).items():
                if not isinstance(config, DigitalWire):
                    continue
                for pin in config.to:
                    if pin.device in waiting and pin.device not in reached:
                        waits[pin.device] = Wire(sender, name, config)
                        reached.add(pin.device)
                        pending.append(pin.device)
        return Chain(starters=starters, waits=waits, unstarted=tuple(sorted(waiting - reached)))


PropertyName = Annotated[str, Field(min_length=1)]
"""The name of a property that a device class declares, such as ``exposure_time_ms``."""


class ChannelConfig(FrozenModel):
    """What 1 camera images in a profile: its light source, and the sensor region that the camera reads out."""

    illumination: DeviceUid
    fov: AreaROI
    label: str | None = None


@dataclass(frozen=True)
class LightSetting:
    """The light of 1 capture: the position of every device that a rule sets, and each camera's magnification and
    band, in nm."""

    positions: dict[DeviceUid, AxisPosition]
    magnification: dict[DeviceUid, float]
    band: dict[DeviceUid, tuple[float | None, float | None] | None]


class ProfileConfig(FrozenModel):
    """What is on at the same moment, and all that it needs to run. ``channels`` has 1 entry for each camera that is
    on. ``positions`` gives the position of each device that this profile sets. ``timelines`` gives what each signal
    generator plays, and ``spacing`` the µm between frames along the scan axis."""

    channels: dict[DeviceUid, ChannelConfig] = Field(min_length=1)
    positions: dict[DeviceUid, AxisPosition] = Field(default_factory=dict)
    props: dict[DeviceUid, dict[PropertyName, Any]] = Field(default_factory=dict)
    setup: dict[DeviceUid, list[CommandRequest]] = Field(default_factory=dict)
    timelines: dict[DeviceUid, Timeline] = Field(default_factory=dict)
    spacing: PositiveFloat
    desc: str = ""
    label: str | None = None

    def light_paths(self, hal: HALConfig) -> dict[DeviceUid, list[LightPath]]:
        """Every way the light of each channel goes from its source, through the sample, to its camera."""
        return {camera: hal.light_paths(channel.illumination, camera) for camera, channel in self.channels.items()}

    def path_nodes(self, hal: HALConfig) -> set[str]:
        """Every node on the light paths of the channels."""
        return {node for paths in self.light_paths(hal).values() for path in paths for node in path.nodes}

    def settable_devices(self, hal: HALConfig) -> set[str]:
        """The devices that ``props`` may set: those on the light paths."""
        return {node for node in self.path_nodes(hal) if node in hal.device_uids}

    def light_setting(self, hal: HALConfig, picks: Mapping[str, AxisPosition]) -> LightSetting:
        """The light of 1 capture. ``picks`` gives the position of each device that the instrument holds. Raise
        ``ValueError`` when a camera gets no light, or its lit paths do not agree on 1 magnification."""
        chosen = {**picks, **self.positions}
        setting = LightSetting(positions={}, magnification={}, band={})
        for camera, paths in self.light_paths(hal).items():
            lit = _lit(paths, chosen)
            if not lit:
                raise ValueError(f"No light reaches '{camera}' with {_given(paths, chosen)}.")
            magnifications = {path.magnification for path in lit}
            magnification = magnifications.pop() if len(magnifications) == 1 else None
            if magnification is None:
                raise ValueError(f"The lit light paths to '{camera}' do not give 1 magnification.")
            setting.magnification[camera] = magnification
            bands = {path.band for path in lit}
            setting.band[camera] = bands.pop() if len(bands) == 1 else None
            on_paths = {node for path in lit for node in path.nodes}
            setting.positions.update({node: value for node, value in chosen.items() if node in on_paths})
        return setting

    def violations(self, hal: HALConfig) -> list[Violation]:
        """Return the problems of this profile against ``hal``."""
        violations, paths = self._channel_violations(hal)
        if violations:  # the checks below read the light paths, so a wrong channel would repeat as their problems
            return [*violations, *self._timeline_violations(hal)]
        nodes = {node for found in paths.values() for path in found for node in path.nodes}
        elements = hal.optics.elements()

        position_violations = [
            Violation(
                code="profile.position.unexpected",
                msg=f"'{device}' is not a device on the light paths of this profile's channels.",
                loc=("positions", device),
            )
            for device in self.positions
            if device not in nodes or device not in elements or device not in hal.device_uids
        ]
        position_violations += [
            Violation(code="profile.position_invalid", msg=problem, loc=("positions", device))
            for device, value in self.positions.items()
            if device in nodes and device in elements and (problem := hal.position_problem(device, value)) is not None
        ]
        violations += position_violations
        if not position_violations:
            # A device that this profile does not set can be at any position here: the instrument can set it.
            violations += [
                Violation(
                    code="profile.channel.dark",
                    msg=f"No light reaches '{camera}' with {_given(found, self.positions)}.",
                    loc=("channels", camera),
                )
                for camera, found in paths.items()
                if not _lit(found, self.positions)
            ]

        for device in self.props:
            if device in nodes and device in hal.device_uids:
                continue
            if device not in nodes:
                msg = f"'{device}' is not on the light paths of this profile's channels."
            else:
                msg = f"'{device}' is a part, so it has no settings."
            violations.append(Violation(code="profile.props_inactive", msg=msg, loc=("props", device)))
        violations += [
            Violation(
                code="profile.setup_inactive",
                msg=f"'{device}' is not a device on the light paths of this profile's channels.",
                loc=("setup", device),
            )
            for device in self.setup
            if device not in nodes or device not in hal.device_uids
        ]
        return [*violations, *self._timeline_violations(hal)]

    def _channel_violations(self, hal: HALConfig) -> tuple[list[Violation], dict[DeviceUid, list[LightPath]]]:
        """The problems of the channels, and the light paths of those that have none."""
        cameras, sources = hal.optics.detectors(), hal.optics.sources()
        violations: list[Violation] = []
        paths: dict[DeviceUid, list[LightPath]] = {}
        for camera, channel in self.channels.items():
            loc = ("channels", camera)
            if camera not in cameras:
                msg = f"'{camera}' is not a detector of hal.optics: a detector gives 'width' and 'height'."
                violations.append(Violation(code="profile.channel.not_detector", msg=msg, loc=loc))
            elif channel.illumination not in sources:
                msg = f"'{channel.illumination}' is not a light source: a node of hal.optics sends light to it."
                violations.append(Violation(code="profile.channel.not_source", msg=msg, loc=(*loc, "illumination")))
            elif not (found := hal.light_paths(channel.illumination, camera)):
                msg = f"No light path goes from '{channel.illumination}' through the sample to '{camera}'."
                violations.append(Violation(code="profile.channel.no_path", msg=msg, loc=loc))
            else:
                paths[camera] = found
        return violations, paths

    def _timeline_violations(self, hal: HALConfig) -> list[Violation]:
        """The problems of the timelines, and each trigger wire of the scan that this profile does not play."""
        violations: list[Violation] = []
        for generator, timeline in self.timelines.items():
            if not (wires := hal.wiring.outputs(generator)):
                msg = f"'{generator}' sends no wires in hal.wiring, so it has nothing to play."
                violations.append(Violation(code="profile.timeline.no_wires", msg=msg, loc=("timelines", generator)))
            else:
                violations += under(("timelines", generator), timeline.violations(wires))

        chain, generators = hal.chain(), hal.generators()
        needed = dict.fromkeys([*self.channels, *self.timelines, hal.stage.device(hal.scan.axis)])
        for device in needed:
            if (wire := chain.waits.get(device)) is None or wire.sender not in generators:
                continue
            timeline = self.timelines.get(wire.sender)
            if timeline is None or wire.name not in timeline.signals:
                violations.append(
                    Violation(
                        code="profile.trigger_not_played",
                        msg=f"'{device}' waits on {wire.sender}'s {wire.name}, and this profile plays no signal on it.",
                        loc=("timelines", wire.sender),
                    )
                )
        return violations


def _collinear(points: list[Vec2D]) -> bool:
    a, b = points[0], points[1]
    return all((b.x - a.x) * (p.y - a.y) == (b.y - a.y) * (p.x - a.x) for p in points[2:])


def _unique(points: list[Vec2D], name: str) -> None:
    if duplicates := repeated(points):
        raise ValueError(f"{name} points must be unique (repeated: {duplicates})")


class BoundingBox(FrozenModel):
    """The smallest rectangle that holds the points."""

    kind: Literal["bounding_box"]
    points: list[Vec2D] = Field(min_length=2)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if len({p.x for p in self.points}) < 2 or len({p.y for p in self.points}) < 2:
            raise ValueError("bounding-box points must span a width and a height")
        return self


class ConvexHull(FrozenModel):
    """The smallest convex shape that holds the points."""

    kind: Literal["convex_hull"]
    points: list[Vec2D] = Field(min_length=3)

    @model_validator(mode="after")
    def _check(self) -> Self:
        points = self.points
        _unique(points, "convex-hull")
        if _collinear(points):
            raise ValueError("convex-hull points must not all lie on 1 line")
        return self


class ExplicitPoints(FrozenModel):
    """1 capture centered on each point."""

    kind: Literal["explicit_points"]
    points: list[Vec2D] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _unique(self.points, "explicit")
        return self


type XYShape = Annotated[BoundingBox | ConvexHull | ExplicitPoints, Field(discriminator="kind")]


class Surface(FrozenModel):
    """Measured heights ``z`` at XY positions, joined by flat triangles."""

    points: list[Vec3D] = Field(min_length=3)

    @model_validator(mode="after")
    def _check(self) -> Self:
        points = [p.xy for p in self.points]
        _unique(points, "surface")
        if _collinear(points):
            raise ValueError("surface points must not all lie on 1 line")
        return self


type Bound = Annotated[float, Field(allow_inf_nan=False)] | Surface
"""A flat height in µm, or a surface."""


class ZBounds(FrozenModel):
    start: Bound
    end: Bound

    @model_validator(mode="after")
    def _check(self) -> Self:
        if isinstance(self.start, float) and isinstance(self.end, float) and not self.start < self.end:
            raise ValueError(f"z start ({self.start}) must be below z end ({self.end})")
        return self


class Region(FrozenModel):
    """Which part of the sample to image: an XY shape and Z bounds, in µm."""

    xy: XYShape
    z: ZBounds


type AxisPath = Literal["forward", "alternate"]
"""``forward`` always starts from the same end; ``alternate`` goes back and forth."""


class Grid(FrozenModel):
    """Tiles in rows and columns. The tiled axes, fastest first, each with how it goes."""

    kind: Literal["grid"]
    axes: list[dict[SpecimenAxis, AxisPath]] = Field(min_length=1)

    @field_validator("axes")
    @classmethod
    def _one_axis_each(cls, value: list[dict[SpecimenAxis, AxisPath]]) -> list[dict[SpecimenAxis, AxisPath]]:
        if any(len(entry) != 1 for entry in value):
            raise ValueError("each grid entry names exactly 1 axis, such as {x: alternate}")
        return value

    @property
    def axis_order(self) -> list[SpecimenAxis]:
        """The tiled axes, fastest first."""
        return [axis for entry in self.axes for axis in entry]


class NearestNeighbor(FrozenModel):
    kind: Literal["nearest_neighbor"]


class Optimized(FrozenModel):
    """The shortest path found by improving the nearest-neighbor path."""

    kind: Literal["optimized"]


class AsGiven(FrozenModel):
    """In the order of the explicit points."""

    kind: Literal["as_given"]


type TileOrder = Annotated[Grid | NearestNeighbor | Optimized | AsGiven, Field(discriminator="kind")]


class TaskPath(FrozenModel):
    """How the axes go: the axis that moves inside each capture, and the tiles between captures."""

    scan: dict[SpecimenAxis, AxisPath]
    tiles: TileOrder


type Iteration = Literal["position_major", "profile_major"]


class TaskSettings(FrozenModel):
    """The settings a task can take from ``config.default.task``. ``overlap`` is per tiled axis."""

    overlap: dict[SpecimenAxis, Portion]
    path: TaskPath
    iteration: Iteration

    def violations(self, scan: Scan) -> list[Violation]:
        """Return each axis here that does not fit the axis that ``scan`` moves and those it tiles."""
        tiled = scan.tiled()
        violations = assignment_violations(
            expected=tiled,
            assigned=self.overlap,
            loc=("overlap",),
            code="task.overlap",
            label="tiled-axis overlap",
        )
        violations += assignment_violations(
            expected=[scan.axis],
            assigned=self.path.scan,
            loc=("path", "scan"),
            code="task.path.scan",
            label="scan-axis path",
        )
        tiles = self.path.tiles
        if isinstance(tiles, Grid):
            grid_loc = ("path", "tiles", "axes")
            if sorted(tiles.axis_order) != sorted(tiled):
                violations.append(
                    Violation(
                        code="task.path.grid_axes",
                        msg=f"The grid must list each tiled axis once: {tiled}.",
                        loc=grid_loc,
                    )
                )
            elif tiles.axes[-1][tiles.axis_order[-1]] == "alternate":
                violations.append(
                    Violation(
                        code="task.path.slowest_alternate",
                        msg=(
                            f"'{tiles.axis_order[-1]}' is the slowest tiled axis, "
                            "so it never repeats and cannot alternate."
                        ),
                        loc=(*grid_loc, len(tiles.axes) - 1),
                    )
                )
        return violations


class Task(TaskSettings):
    """1 entry in the plan, stored complete."""

    id: TaskId
    region: Region
    profiles: Annotated[UniqueList[ProfileId], Field(min_length=1)]

    @classmethod
    def complete(cls, data: Mapping[str, Any], defaults: TaskSettings) -> Self:
        """Build a task, taking from ``defaults`` each setting that ``data`` leaves out."""
        filled = defaults.model_dump(mode="json") | dict(data)
        return cls.model_validate(filled)

    def violations(self, scan: Scan) -> list[Violation]:
        violations = super().violations(scan)
        if isinstance(self.region.xy, ExplicitPoints) and scan.axis in ("x", "y"):
            violations.append(
                Violation(
                    code="task.region.explicit_points_untiled",
                    msg="Explicit points place captures in X and Y, so X and Y must both be tiled.",
                    loc=("region", "xy"),
                )
            )
        if isinstance(self.path.tiles, AsGiven) and not isinstance(self.region.xy, ExplicitPoints):
            violations.append(
                Violation(
                    code="task.path.as_given_needs_points",
                    msg="'as_given' keeps the order of explicit points, and this region has none.",
                    loc=("path", "tiles"),
                )
            )
        return violations


def _lit(paths: list[LightPath], chosen: Mapping[str, AxisPosition]) -> list[LightPath]:
    """The paths that stay lit with the devices in ``chosen`` at their positions."""
    return [path for path in paths if all(chosen.get(device, at) == at for device, at in path.positions.items())]


def _given(paths: list[LightPath], chosen: Mapping[str, AxisPosition]) -> str:
    on_paths = {node for path in paths for node in path.nodes}
    return ", ".join(f"{device} at {value}" for device, value in chosen.items() if device in on_paths) or "no positions"


class StageFollowRule(FrozenModel):
    """A device follows the stage. Along ``axis``, it takes the positions in ``order``, 1 after the other. ``at``
    gives the points, in µm, where it changes to the next position; within ``margin`` of a point, it keeps the
    position it has."""

    axis: SpecimenAxis
    order: Annotated[UniqueList[str], Field(min_length=2)]
    at: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(min_length=1)
    margin: float = Field(default=0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if any(b <= a for a, b in pairwise(self.at)):
            raise ValueError("'at' must rise from 1 point to the next")
        if len(self.at) != len(self.order) - 1:
            points = len(self.order) - 1
            raise ValueError(f"{len(self.order)} positions in 'order' need {points} in 'at', got {len(self.at)}")
        return self

    def position(self, coordinate: float, *, previous: str | None = None) -> str:
        """The position at ``coordinate`` on ``axis``. Next to ``previous``, it stays there until ``coordinate``
        passes the point between them by the margin."""
        index = bisect_right(self.at, coordinate)
        if previous in self.order and abs(index - (before := self.order.index(previous))) == 1:
            point = self.at[min(index, before)]
            stays = coordinate < point + self.margin if index > before else coordinate >= point - self.margin
            if stays:
                index = before
        return self.order[index]


class State(InstrumentState[HALConfig]):
    """The state of a SPIM instrument. ``positions`` gives the position of each device that the instrument sets, the
    same for every profile: 1 position, or the rule by which the device follows the stage. ``plan`` is the tasks to
    run."""

    task: TaskSettings
    positions: dict[DeviceUid, StageFollowRule | AxisPosition] = Field(default_factory=dict)
    profiles: dict[ProfileId, ProfileConfig] = Field(min_length=1)
    plan: Annotated[list[Task], NotDefault] = Field(default_factory=list)

    @field_validator("plan")
    @classmethod
    def _unique_task_ids(cls, plan: list[Task]) -> list[Task]:
        if duplicates := repeated(task.id for task in plan):
            raise ValueError(f"task ids must be unique (repeated: {duplicates})")
        return plan

    def violations(self, hal: HALConfig) -> list[Violation]:
        """Return the problems of this state against ``hal``."""
        violations = under(("task",), self.task.violations(hal.scan))
        violations += under(("positions",), self._position_violations(hal))
        for profile_id, profile in self.profiles.items():
            violations += under(("profiles", profile_id), profile.violations(hal))
        violations += under(("profiles",), self._level_violations(hal))
        for index, task in enumerate(self.plan):
            found = task.violations(hal.scan)
            found += [
                not_configured("Profile", profile_id, code="task.profile_missing", loc=("profiles", profile_index))
                for profile_index, profile_id in enumerate(task.profiles)
                if profile_id not in self.profiles
            ]
            violations += under(("plan", index), found)
        return violations

    def _position_violations(self, hal: HALConfig) -> list[Violation]:
        """The problems of the instrument's own positions: each names a device of the optical graph and a position
        that the device has, and a device does not follow the axis that a capture moves."""
        elements = hal.optics.elements()
        violations: list[Violation] = []
        for device, position in self.positions.items():
            if device not in elements or device not in hal.device_uids:
                msg = f"'{device}' is not a device of hal.optics."
                violations.append(Violation(code="positions.unexpected", msg=msg, loc=(device,)))
            elif not isinstance(position, StageFollowRule):
                if (problem := hal.position_problem(device, position)) is not None:
                    violations.append(Violation(code="positions.invalid", msg=problem, loc=(device,)))
            else:
                violations += [
                    Violation(code="positions.invalid", msg=problem, loc=(device, "order", index))
                    for index, label in enumerate(position.order)
                    if (problem := hal.position_problem(device, label)) is not None
                ]
                if position.axis == hal.scan.axis:
                    msg = f"A capture moves '{position.axis}', so '{device}' cannot follow it; follow a tiled axis."
                    violations.append(Violation(code="positions.follows_scan_axis", msg=msg, loc=(device, "axis")))
        return violations

    def _level_violations(self, hal: HALConfig) -> list[Violation]:
        """The problems between the instrument's positions and those of the profiles. A device gets its position
        from 1 level only. A device whose position changes the light, on a profile's light paths, gets a position.
        A device that 1 profile sets, each profile with it on its light paths sets."""
        elements, selectors = hal.optics.elements(), hal.selectors()
        in_a_profile = {device for profile in self.profiles.values() for device in profile.positions}
        violations: list[Violation] = []
        for profile_id, profile in self.profiles.items():
            nodes = profile.path_nodes(hal)
            for device in profile.positions:
                if device in self.positions:
                    msg = f"'{device}' is set in the instrument's positions and in this profile. Set it in 1 place."
                    code = "profile.position.two_levels"
                    violations.append(Violation(code=code, msg=msg, loc=(profile_id, "positions", device)))
            for device in sorted(nodes):
                if device in self.positions or device in profile.positions or device not in elements:
                    continue
                if device in selectors:
                    msg = (
                        f"'{device}' is on the light paths of this profile, and no position is given. Give it here, "
                        "or in the instrument's positions."
                    )
                    code = "profile.position.missing"
                elif device in in_a_profile:
                    msg = f"A different profile sets '{device}', and it is on the light paths of this profile too."
                    code = "profile.position.not_in_all_profiles"
                else:
                    continue
                violations.append(Violation(code=code, msg=msg, loc=(profile_id, "positions", device)))
        return violations


class Config(InstrumentConfig[HALConfig, State]):
    """The ``config.yaml`` of a SPIM instrument."""

    KIND: ClassVar[str] = "vxl.instruments.spim"


Template = InstrumentTemplate[HALConfig, State]
"""A shipped SPIM design: a SPIM instrument file without an ID or a name."""
