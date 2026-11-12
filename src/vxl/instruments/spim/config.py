"""The files of a SPIM instrument: ``rig.yaml``, ``default.yaml``, ``state.json`` and presets."""

from bisect import bisect_right
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise, product
from typing import Annotated, Any, Literal, Self

from pydantic import Field, PositiveFloat, field_validator, model_validator
from rigup.device.schema import CommandRequest
from vxlib.schema import FrozenModel, UniqueList, identifier, repeated
from vxlib.units import Portion
from vxlib.vector import Vec2D, Vec3D

from vxl.core.instrument.config import (
    DeviceUid,
    DigitalWire,
    InstrumentConfig,
    InstrumentState,
    NotDefault,
    SpecimenAxis,
    Stage,
    Wire,
)
from vxl.core.instrument.errors import Violation, Violations
from vxl.core.instrument.samples import render
from vxl.core.instrument.signals import Timeline
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
    """What starts each device of 1 profile in 1 capture. ``starters`` start by themselves: the pacer, or every
    generator when the program paces. ``waits`` gives the wire whose pulses start each other device. ``unstarted``
    lists each camera, generator or stepping axis that nothing starts."""

    starters: tuple[DeviceUid, ...]
    waits: Mapping[DeviceUid, Wire]
    unstarted: tuple[DeviceUid, ...]


class SPIMConfig(InstrumentConfig, frozen=True):
    """The ``rig.yaml`` of a SPIM instrument. ``scan`` says how 1 capture runs."""

    scan: Scan

    def violations(self) -> Violations:
        violations = super().violations()
        violations += self._software_violations()
        violations += self._scan_violations().under("scan")
        return violations

    def trigger_chain(self, cameras: Collection[DeviceUid], generators: Collection[DeviceUid]) -> Chain:
        """What starts each device in 1 capture with ``cameras`` and ``generators``, worked out from ``scan`` and the
        wires. Follow the digital wires from the pacer. Each camera, generator, or axis that steps waits on the first
        wire that reaches it. A starter never waits, an axis that sweeps never waits, and with ``software`` the
        program moves the axis. A wire to any other device, such as a laser's gate, starts nothing."""
        by_program = self.scan.pacer == SOFTWARE
        waiting = {*cameras, *generators}
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

    def _software_violations(self) -> Violations:
        violations = Violations()
        if SOFTWARE in self.component_uids:
            msg = "'software' names the program as the pacer of a scan, so no device takes it."
            violations.add("rig.reserved_name", msg, "components", SOFTWARE)
        return violations

    def _scan_violations(self) -> Violations:
        violations = Violations()
        pacer = self.scan.pacer
        if pacer != SOFTWARE and pacer not in self.component_uids:
            violations.append(Violation.not_configured("Device", pacer, code="rig.scan.pacer_missing", loc=("pacer",)))
        return violations


PropertyName = Annotated[str, Field(min_length=1)]
"""The name of a property that a device class declares, such as ``exposure_time_ms``."""


class Channel(FrozenModel):
    """What 1 camera images in a profile: its light source, and the sensor region that the camera reads out."""

    illumination: DeviceUid
    fov: AreaROI
    label: str | None = None


class Profile(FrozenModel):
    """What is on at the same moment, and all that it needs to run. ``channels`` has 1 entry for each camera that is
    on. ``positions`` gives the position of each device that this profile sets. ``timelines`` gives what each signal
    generator plays, and ``spacing`` the µm between frames along the scan axis."""

    channels: dict[DeviceUid, Channel] = Field(min_length=1)
    positions: dict[DeviceUid, AxisPosition] = Field(default_factory=dict)
    props: dict[DeviceUid, dict[PropertyName, Any]] = Field(default_factory=dict)
    setup: dict[DeviceUid, list[CommandRequest]] = Field(default_factory=dict)
    timelines: dict[DeviceUid, Timeline] = Field(default_factory=dict)
    spacing: PositiveFloat
    desc: str = ""
    label: str | None = None

    def violations(self, config: SPIMConfig) -> Violations:
        """Return the problems of this profile against ``config``."""
        violations = self._channel_violations(config)
        if violations:  # the checks below read the light paths, so a wrong channel would repeat as their problems
            violations += self._timeline_violations(config)
            return violations
        nodes = self.path_nodes(config)

        positions = self._position_violations(config, nodes)
        violations += positions
        if not positions:
            violations += self._dark_violations(config)

        for device in self.props:
            if device in nodes and device in config.component_uids:
                continue
            if device not in nodes:
                msg = f"'{device}' is not on the light paths of this profile's channels."
            else:
                msg = f"'{device}' is a part, so it has no settings."
            violations.add("profile.props_inactive", msg, "props", device)
        for device in self.setup:
            if device not in nodes or device not in config.component_uids:
                msg = f"'{device}' is not a device on the light paths of this profile's channels."
                violations.add("profile.setup_inactive", msg, "setup", device)
        violations += self._timeline_violations(config)
        violations += self._chain_violations(config)
        return violations

    def path_nodes(self, config: SPIMConfig) -> set[str]:
        """Every node on the light paths of the channels, on both sides of the sample, with each device at any
        position."""
        nodes: set[str] = set()
        for camera, channel in self.channels.items():
            for path in (*config.illumination_paths(channel.illumination, {}), *config.detection_paths(camera, {})):
                nodes.update(path.nodes)
        return nodes

    def _position_violations(self, config: SPIMConfig, nodes: set[str]) -> Violations:
        """The problems of the positions: each names a device on the light paths."""
        elements = config.optics.elements()
        violations = Violations()
        for device in self.positions:
            if device not in nodes or device not in elements or device not in config.component_uids:
                msg = f"'{device}' is not a device on the light paths of this profile's channels."
                violations.add("profile.position.unexpected", msg, "positions", device)
        return violations

    def _channel_violations(self, config: SPIMConfig) -> Violations:
        """The problems of the channels: each names a camera and a light source, and the light can go from the
        source to the sample and from the sample to the camera, with each device at any position."""
        cameras, sources = config.optics.detectors(), config.optics.sources()
        violations = Violations()
        for camera, channel in self.channels.items():
            if camera not in cameras:
                msg = f"'{camera}' is not a detector of 'optics': a detector gives 'width' and 'height'."
                violations.add("profile.channel.not_detector", msg, "channels", camera)
            elif channel.illumination not in sources:
                msg = f"'{channel.illumination}' is not a light source: a node of 'optics' sends light to it."
                violations.add("profile.channel.not_source", msg, "channels", camera, "illumination")
            elif not config.illumination_paths(channel.illumination, {}):
                msg = f"No light path goes from '{channel.illumination}' to the sample."
                violations.add("profile.channel.no_path", msg, "channels", camera)
            elif not config.detection_paths(camera, {}):
                msg = f"No light path goes from the sample to '{camera}'."
                violations.add("profile.channel.no_path", msg, "channels", camera)
        return violations

    def _dark_violations(self, config: SPIMConfig) -> Violations:
        """Each camera that gets no light with the positions of this profile. A device that this profile does not
        set can be at any position: the instrument can set it."""
        violations = Violations()
        for camera, channel in self.channels.items():
            if not config.illumination_paths(channel.illumination, self.positions):
                msg = f"No light of '{channel.illumination}' reaches the sample with {self._given()}."
            elif not config.detection_paths(camera, self.positions):
                msg = f"No light goes from the sample to '{camera}' with {self._given()}."
            else:
                continue
            violations.add("profile.channel.dark", msg, "channels", camera)
        return violations

    def _timeline_violations(self, config: SPIMConfig) -> Violations:
        violations = Violations()
        for generator, timeline in self.timelines.items():
            if not (wires := config.wiring.outputs(generator)):
                msg = f"'{generator}' sends no wires in 'wiring', so it has nothing to play."
                violations.add("profile.timeline.no_wires", msg, "timelines", generator)
                continue
            found = timeline.violations(wires)
            if not found:  # the samples of a wrong timeline would repeat its problems
                found = render(timeline, wires).violations
            violations += found.under("timelines", generator)
        return violations

    def _chain_violations(self, config: SPIMConfig) -> Violations:
        """Each device of this profile that nothing starts, and each device that waits on a wire with no pulses. A
        stage axis or a camera makes the pulses of its own wires. The profile must play a signal on any other wire."""
        violations = Violations()
        if config.scan.pacer != SOFTWARE and config.scan.pacer not in config.component_uids:
            return violations
        chain = config.trigger_chain(self.channels, self.timelines)
        for device in chain.unstarted:
            msg = f"Nothing starts '{device}': no wire in the chain from the pacer reaches it."
            violations.add("profile.unstarted", msg)
        own_pulses = {*config.stage.devices().values(), *config.optics.detectors()}
        for device, wire in chain.waits.items():
            if wire.sender in own_pulses:
                continue
            timeline = self.timelines.get(wire.sender)
            if timeline is None or wire.name not in timeline.signals:
                msg = f"'{device}' waits on {wire.sender}'s {wire.name}, and this profile plays no signal on it."
                violations.add("profile.trigger_not_played", msg, "timelines", wire.sender)
        return violations

    def _given(self) -> str:
        """The positions that this profile sets, as words."""
        return ", ".join(f"{device} at {value}" for device, value in self.positions.items()) or "no positions"


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


class TaskDefaults(FrozenModel):
    """The settings a task can take from the ``task`` of the defaults. ``overlap`` is per tiled axis."""

    overlap: dict[SpecimenAxis, Portion]
    path: TaskPath
    iteration: Iteration

    def violations(self, scan: Scan) -> Violations:
        """Return each axis here that does not fit the axis that ``scan`` moves and those it tiles."""
        tiled = scan.tiled()
        violations = Violations.assignments(
            expected=tiled, assigned=self.overlap, code="task.overlap", label="tiled-axis overlap"
        ).under("overlap")
        violations += Violations.assignments(
            expected=[scan.axis], assigned=self.path.scan, code="task.path.scan", label="scan-axis path"
        ).under("path", "scan")
        tiles = self.path.tiles
        if isinstance(tiles, Grid):
            if sorted(tiles.axis_order) != sorted(tiled):
                msg = f"The grid must list each tiled axis once: {tiled}."
                violations.add("task.path.grid_axes", msg, "path", "tiles", "axes")
            elif tiles.axes[-1][tiles.axis_order[-1]] == "alternate":
                msg = f"'{tiles.axis_order[-1]}' is the slowest tiled axis, so it never repeats and cannot alternate."
                violations.add("task.path.slowest_alternate", msg, "path", "tiles", "axes", len(tiles.axes) - 1)
        return violations


class Task(TaskDefaults):
    """1 entry in the plan, stored complete."""

    id: TaskId
    region: Region
    profiles: Annotated[UniqueList[ProfileId], Field(min_length=1)]

    @classmethod
    def complete(cls, data: Mapping[str, Any], defaults: TaskDefaults) -> Self:
        """Build a task, taking from ``defaults`` each setting that ``data`` leaves out."""
        filled = defaults.model_dump(mode="json") | dict(data)
        return cls.model_validate(filled)

    def violations(self, scan: Scan) -> Violations:
        violations = super().violations(scan)
        if isinstance(self.region.xy, ExplicitPoints) and scan.axis in ("x", "y"):
            msg = "Explicit points place captures in X and Y, so X and Y must both be tiled."
            violations.add("task.region.explicit_points_untiled", msg, "region", "xy")
        if isinstance(self.path.tiles, AsGiven) and not isinstance(self.region.xy, ExplicitPoints):
            msg = "'as_given' keeps the order of explicit points, and this region has none."
            violations.add("task.path.as_given_needs_points", msg, "path", "tiles")
        return violations


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


class SPIMState(InstrumentState, frozen=True):
    """The state of a SPIM instrument. ``positions`` gives the position of each device that the instrument sets, the
    same for every profile: 1 position, or the rule by which the device follows the stage. ``plan`` is the tasks to
    run."""

    task: TaskDefaults
    positions: dict[DeviceUid, StageFollowRule | AxisPosition] = Field(default_factory=dict)
    profiles: dict[ProfileId, Profile] = Field(min_length=1)
    plan: Annotated[list[Task], NotDefault] = Field(default_factory=list)

    @field_validator("plan")
    @classmethod
    def _unique_task_ids(cls, plan: list[Task]) -> list[Task]:
        if duplicates := repeated(task.id for task in plan):
            raise ValueError(f"task ids must be unique (repeated: {duplicates})")
        return plan

    def violations(self, config: InstrumentConfig) -> Violations:
        if not isinstance(config, SPIMConfig):
            raise TypeError(f"a SPIMState is for a SPIMConfig, not a {type(config).__name__}")
        violations = self.task.violations(config.scan).under("task")
        violations += self._position_violations(config).under("positions")
        for profile_id, profile in self.profiles.items():
            violations += profile.violations(config).under("profiles", profile_id)
        violations += self._level_violations(config).under("profiles")
        violations += self._magnification_violations(config).under("profiles")
        for index, task in enumerate(self.plan):
            found = task.violations(config.scan)
            for profile_index, profile_id in enumerate(task.profiles):
                if profile_id not in self.profiles:
                    loc = ("profiles", profile_index)
                    found.append(Violation.not_configured("Profile", profile_id, code="task.profile_missing", loc=loc))
            violations += found.under("plan", index)
        return violations

    def _position_violations(self, config: SPIMConfig) -> Violations:
        """The problems of the instrument's own positions: each names a device of the optical graph, and a device
        does not follow the axis that a capture moves."""
        elements = config.optics.elements()
        violations = Violations()
        for device, position in self.positions.items():
            if device not in elements or device not in config.component_uids:
                violations.add("positions.unexpected", f"'{device}' is not a device of 'optics'.", device)
            elif isinstance(position, StageFollowRule) and position.axis == config.scan.axis:
                msg = f"A capture moves '{position.axis}', so '{device}' cannot follow it; follow a tiled axis."
                violations.add("positions.follows_scan_axis", msg, device, "axis")
        return violations

    def _level_violations(self, config: SPIMConfig) -> Violations:
        """The problems between the instrument's positions and those of the profiles. A device gets its position
        from 1 level only. A device that sends the light a different way at each position, on a profile's light
        paths, gets a position. A device that 1 profile sets, each profile with it on its light paths sets."""
        elements = config.optics.elements()
        in_a_profile = {device for profile in self.profiles.values() for device in profile.positions}
        violations = Violations()
        for profile_id, profile in self.profiles.items():
            nodes = profile.path_nodes(config)
            for device in profile.positions:
                if device in self.positions:
                    msg = f"'{device}' is set in the instrument's positions and in this profile. Set it in 1 place."
                    violations.add("profile.position.two_levels", msg, profile_id, "positions", device)
            for device in sorted(nodes):
                if device in self.positions or device in profile.positions or device not in elements:
                    continue
                if device in config.component_uids and isinstance(elements[device].to, dict):
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
                violations.add(code, msg, profile_id, "positions", device)
        return violations

    def _magnification_violations(self, config: SPIMConfig) -> Violations:
        """Each camera of a profile gets 1 magnification from the parts between the sample and the camera. A device
        that follows the stage is checked at each position of its rule."""
        violations = Violations()
        for profile_id, profile in self.profiles.items():
            problems: dict[DeviceUid, str] = {}
            for held in self._held_positions():
                for camera in profile.channels:
                    paths = config.detection_paths(camera, {**held, **profile.positions})
                    given = sorted({path.magnification for path in paths if path.magnification is not None})
                    if any(path.magnification is None for path in paths):
                        msg = f"A light path to '{camera}' has no part that gives a magnification."
                    elif len(given) > 1:
                        msg = f"The light paths to '{camera}' give more than 1 magnification: {given}."
                    else:
                        continue
                    problems.setdefault(camera, msg)
            for camera, msg in problems.items():
                violations.add("profile.channel.magnification", msg, profile_id, "channels", camera)
        return violations

    def _held_positions(self) -> list[dict[DeviceUid, AxisPosition]]:
        """Each set of positions that the instrument can give its devices. A device that follows the stage takes
        each position of its rule."""
        choices: list[Sequence[AxisPosition]] = [
            position.order if isinstance(position, StageFollowRule) else [position]
            for position in self.positions.values()
        ]
        return [dict(zip(self.positions, chosen, strict=True)) for chosen in product(*choices)]
