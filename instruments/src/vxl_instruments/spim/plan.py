"""The plan of the tasks: what a screen shows before a run, and the volumes that a run follows."""

import hashlib
import itertools
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import TypeAdapter
from vxlib.schema import FrozenModel
from vxlib.vector import Span, Transform, Vec3D

from vxl.devices.base import DeviceId
from vxl.devices.camera import AreaROI, CameraSensor
from vxl.instrument.geometry import AxisRun, camera_frame
from vxl.instrument.state import ProfileId, StageFollowRule, TaskId
from vxl.optics import AxisPosition, SpecimenAxis

from .config import SPIMConfig, SPIMProfile
from .state import SPIMState
from .task import ExplicitPoints, Grid, Region, SPIMTask, TaskDefaults

type FootprintId = str
"""A footprint's id: 8 hex characters of the SHA-256 of its content. The same footprint always has the same id."""

type Stop = tuple[int, int, int]
"""1 stop: its index into the values of the 1st and the 2nd tiled axis, and the index of its zone."""

type _Setup = tuple[tuple[DeviceId, AxisPosition], ...]

_COUNT_TOLERANCE = 1e-9
_ZERO = Vec3D(z=0.0, y=0.0, x=0.0)


@dataclass(frozen=True)
class Volume:
    """1 profile at 1 tile: the unit that runs, saved as 1 dataset for each camera. The stage starts at ``start`` and
    moves by ``scan``; ``positions`` are set before the scan runs; ``transforms`` give where each camera's pixels
    land."""

    task: TaskId
    profile: ProfileId
    start: Vec3D
    scan: AxisRun
    positions: Mapping[DeviceId, AxisPosition]
    transforms: Mapping[DeviceId, Transform]


class Footprint(FrozenModel):
    """Where 1 camera's pixels land with the stage at 0, for 1 light path, region of interest and binning. Pixel row
    ``r``, column ``c`` has its center at ``origin_um + r * row_um + c * column_um``."""

    camera: DeviceId
    origin_um: Vec3D
    row_um: Vec3D
    column_um: Vec3D
    size_px: dict[Literal["rows", "columns"], int]

    @classmethod
    def of(cls, camera: DeviceId, frame: Transform) -> Self:
        """The footprint of 1 frame of ``camera``: an array of shape (1, rows, columns)."""
        _, rows, columns = frame.shape
        size: dict[Literal["rows", "columns"], int] = {"rows": rows, "columns": columns}
        return cls(camera=camera, origin_um=frame.origin, row_um=frame.steps[1], column_um=frame.steps[2], size_px=size)

    @property
    def id(self) -> FootprintId:
        """8 hex characters of the SHA-256 of this footprint as JSON with sorted keys."""
        text = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode()).hexdigest()[:8]

    @property
    def frame(self) -> Transform:
        """1 frame of the camera, as an array of shape (1, rows, columns)."""
        shape = (1, self.size_px["rows"], self.size_px["columns"])
        return Transform(self.origin_um, (_ZERO, self.row_um, self.column_um), shape)


class Zone(FrozenModel):
    """A stretch of the stage where the devices that follow the stage hold 1 position each: those positions, and
    the footprint of each camera of each profile there."""

    devices: dict[DeviceId, AxisPosition]
    cameras: dict[ProfileId, dict[DeviceId, FootprintId]]


class PlannedScan(FrozenModel):
    """Where a forward run takes its first frame on the scan axis, and the frames of each profile's run, its
    ``spacing`` apart. A backward run starts at its last frame."""

    start_um: float
    frames: dict[ProfileId, int]


class PlannedTask(FrozenModel):
    """The plan of 1 task, as a screen draws it. ``overlap`` is each footprint's real overlap with the neighboring
    stops on each tiled axis, as a fraction; an axis with 1 value has none. ``axis_values_um`` holds the stage
    positions that the stops take on each tiled axis, in stage order. ``stops`` are in run order. The visits are the
    stops times the task's profiles, in the order of the task's ``iteration``."""

    scan: PlannedScan
    overlap: dict[FootprintId, dict[SpecimenAxis, float]]
    zones: list[Zone]
    axis_values_um: dict[SpecimenAxis, list[float]]
    stops: list[Stop]


class Unplanned(FrozenModel):
    """Why a task has no plan. The code is ``task.plan.sensor_missing`` while a camera of the task has not reported its
    sensor, and ``task.plan.failed`` for any other reason."""

    code: Literal["task.plan.sensor_missing", "task.plan.failed"]
    msg: str


@dataclass(frozen=True)
class TaskPlans:
    """The plan of every task, from 1 state and the sensors that the cameras reported: the footprints that the plans
    name, each task's plan or the reason it has none, and the volumes of the planned tasks in the order they run."""

    footprints: dict[FootprintId, Footprint]
    tasks: dict[TaskId, PlannedTask | Unplanned]
    volumes: tuple[Volume, ...]

    @property
    def fingerprint(self) -> str | None:
        """12 hex characters of the SHA-256 of the volumes as JSON with sorted keys; ``None`` while a task has no
        plan. The same volumes always give the same fingerprint."""
        if any(isinstance(planned, Unplanned) for planned in self.tasks.values()):
            return None
        data = TypeAdapter(list[Volume]).dump_python(list(self.volumes), mode="json")
        text = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode()).hexdigest()[:12]


class Planner:
    """Plans the tasks of a SPIM instrument from its config, its state and the sensors of its cameras.

    Stops are spaced by the area that every camera of the task sees in every setup the task uses: each profile, at
    each position that a device which follows the stage takes at a stop. On the scan axis every camera's run reaches
    past both ends of the region."""

    def __init__(self, config: SPIMConfig, state: SPIMState, sensors: Mapping[DeviceId, CameraSensor]) -> None:
        self._config = config
        self._state = state
        self._sensors = sensors
        self._fixed = {d: p for d, p in state.positions.items() if not isinstance(p, StageFollowRule)}

    def plan(self) -> TaskPlans:
        """Each task's plan, or the reason it has none. A task that fails to plan for any reason has none; the other
        tasks are planned all the same."""
        footprints: dict[FootprintId, Footprint] = {}
        tasks: dict[TaskId, PlannedTask | Unplanned] = {}
        volumes: list[Volume] = []
        for task in self._state.plan:
            cameras = {c for p in task.profiles for c in self._state.profiles[p].lights()}
            if missing := sorted(cameras - self._sensors.keys()):
                msg = f"{', '.join(missing)} has not reported its sensor."
                tasks[task.id] = Unplanned(code="task.plan.sensor_missing", msg=msg)
                continue
            found: dict[FootprintId, Footprint] = {}
            try:
                planned = self._plan_task(task, found)
                task_volumes = self._volumes(task, planned, found)
            except Exception as error:
                tasks[task.id] = Unplanned(code="task.plan.failed", msg=str(error) or type(error).__name__)
                continue
            footprints.update(found)
            tasks[task.id] = planned
            volumes += task_volumes
        return TaskPlans(footprints, tasks, tuple(volumes))

    def tile(self, profiles: Sequence[ProfileId], picks: Mapping[str, AxisPosition]) -> dict[SpecimenAxis, Span]:
        """The area on each tiled axis that every camera of ``profiles`` sees with the devices at ``picks``, around
        the stage position. Raise ``ValueError`` when they share none."""
        frames = [self._light(self._state.profiles[p], picks)[1] for p in profiles]
        return self._shared((frame for f in frames for frame in f.values()), self._config.scan.tiled())

    def _plan_task(self, task: SPIMTask, footprints: dict[FootprintId, Footprint]) -> PlannedTask:
        """The plan of 1 task, with its footprints added to ``footprints``. The setups start as the one with the
        stage at the region's middle; a setup that a stop takes outside them joins, and the stops are spaced again,
        until every stop takes a setup that the spacing counted."""
        state, scan, region = self._state, self._config.scan, task.region
        followers = [d for d, r in state.positions.items() if isinstance(r, StageFollowRule)]
        middle: dict[SpecimenAxis, float] = {axis: region.extent(axis).middle for axis in ("z", "y", "x")}
        setups: set[_Setup] = {self._setup_at(followers, middle, {})}
        while True:
            seen = {setup: self._footprints(task, dict(setup)) for setup in setups}
            frames = [f for s in seen.values() for cameras in s.values() for f in cameras.values()]
            tile = self._shared((f.frame for f in frames), scan.tiled())
            reached = [b[scan.axis] for b in (f.frame.bounds() for f in frames)]
            span = Span(
                region.extent(scan.axis).low - max(r.high for r in reached),
                region.extent(scan.axis).high - min(r.low for r in reached),
            )
            stages = self._tile_positions(region, task, tile)
            taken: list[_Setup] = []
            previous: Mapping[DeviceId, AxisPosition] = {}
            for stage in stages:
                setup = self._setup_at(followers, {**stage, scan.axis: span.middle}, previous)
                previous = dict(setup)
                taken.append(setup)
            if set(taken) <= setups:
                break
            setups |= set(taken)

        zone_of: dict[_Setup, int] = {}
        zones: list[Zone] = []
        for setup in taken:
            if setup not in zone_of:
                zone_of[setup] = len(zones)
                cameras = {p: {c: f.id for c, f in cs.items()} for p, cs in seen[setup].items()}
                zones.append(Zone(devices=dict(setup), cameras=cameras))
                footprints.update({f.id: f for cs in seen[setup].values() for f in cs.values()})
        tiled = scan.tiled()
        values: dict[SpecimenAxis, list[float]] = {axis: sorted({stage[axis] for stage in stages}) for axis in tiled}
        index = {axis: {value: i for i, value in enumerate(line)} for axis, line in values.items()}
        stops: list[Stop] = [
            (index[tiled[0]][s[tiled[0]]], index[tiled[1]][s[tiled[1]]], zone_of[setup])
            for s, setup in zip(stages, taken, strict=True)
        ]
        used = {f for z in zones for c in z.cameras.values() for f in c.values()}
        overlap = {f: self._overlap(footprints[f], values) for f in sorted(used)}
        counts = {p: math.floor(span.length / state.profiles[p].spacing + _COUNT_TOLERANCE) + 1 for p in task.profiles}
        return PlannedTask(
            scan=PlannedScan(start_um=span.low, frames=counts),
            overlap=overlap,
            zones=zones,
            axis_values_um=values,
            stops=stops,
        )

    def _volumes(
        self, task: SPIMTask, planned: PlannedTask, footprints: Mapping[FootprintId, Footprint]
    ) -> list[Volume]:
        """The volumes that a run of ``task`` follows, in the order they run. With ``alternate`` on the scan axis,
        every 2nd stop runs from the far end back, over the same frame positions; both orders pass each stop's place
        on the tile path, so a stop's direction is the same for every profile."""
        scan, tiled = self._config.scan, self._config.scan.tiled()
        alternate = task.path.scan.get(scan.axis) == "alternate"

        def volume(number: int, stop: Stop, profile_id: ProfileId) -> Volume:
            profile = self._state.profiles[profile_id]
            zone = planned.zones[stop[2]]
            count = planned.scan.frames[profile_id]
            backward = alternate and number % 2 == 1
            first = planned.scan.start_um + profile.spacing * (count - 1) if backward else planned.scan.start_um
            spacing = -profile.spacing if backward else profile.spacing
            run = AxisRun(scan.axis, first, spacing, count, self._sweep_speed(profile, profile_id))
            at = {**{axis: planned.axis_values_um[axis][stop[i]] for i, axis in enumerate(tiled)}, scan.axis: first}
            start = Vec3D(z=at["z"], y=at["y"], x=at["x"])
            frames = {camera: footprints[f].frame for camera, f in zone.cameras[profile_id].items()}
            transforms = {camera: run.transform(frame, start) for camera, frame in frames.items()}
            positions = self._positions(profile, {**self._fixed, **zone.devices})
            return Volume(task.id, profile_id, start, run, positions, transforms)

        if task.iteration == "position_major":
            return [volume(i, stop, p) for i, stop in enumerate(planned.stops) for p in task.profiles]
        return [volume(i, stop, p) for p in task.profiles for i, stop in enumerate(planned.stops)]

    def _setup_at(
        self,
        followers: Sequence[DeviceId],
        stage: Mapping[SpecimenAxis, float],
        previous: Mapping[DeviceId, AxisPosition],
    ) -> _Setup:
        """The position of each device that follows the stage, with the stage at ``stage``."""
        at = self._state.positions_at(stage, previous)
        return tuple((d, at[d]) for d in followers)

    def _footprints(
        self, task: SPIMTask, followers: Mapping[DeviceId, AxisPosition]
    ) -> dict[ProfileId, dict[DeviceId, Footprint]]:
        """Each camera's footprint for each profile of ``task``, with the devices that follow the stage at
        ``followers``."""
        picks = {**self._fixed, **followers}
        found: dict[ProfileId, dict[DeviceId, Footprint]] = {}
        for profile_id in task.profiles:
            _, frames = self._light(self._state.profiles[profile_id], picks)
            found[profile_id] = {camera: Footprint.of(camera, frame) for camera, frame in frames.items()}
        return found

    def _light(
        self, profile: SPIMProfile, picks: Mapping[str, AxisPosition]
    ) -> tuple[dict[DeviceId, AxisPosition], dict[DeviceId, Transform]]:
        """What 1 profile needs with the instrument's devices at ``picks``: the positions to set, and each camera's
        frame at stage position 0. Raise ``ValueError`` when a camera gets no light, has not reported its sensor, or
        the paths from the sample to it do not agree on 1 magnification."""
        positions = self._positions(profile, picks)
        chosen = {**picks, **profile.positions}
        frames: dict[DeviceId, Transform] = {}
        for camera in profile.lights():
            if (sensor := self._sensors.get(camera)) is None:
                raise ValueError(f"'{camera}' has not reported its sensor.")
            region = profile.fov.get(camera, AreaROI(x=0, y=0, w=sensor.size_px.x, h=sensor.size_px.y))
            axes = self._config.camera_axes(camera, chosen)
            frames[camera] = camera_frame(axes, sensor, region, binning=self._binning(profile.props.get(camera, {})))
        return positions, frames

    def _positions(self, profile: SPIMProfile, picks: Mapping[str, AxisPosition]) -> dict[DeviceId, AxisPosition]:
        """The positions that 1 profile sets with the instrument's devices at ``picks``: those on its light paths.
        Raise ``ValueError`` when a camera gets no light."""
        chosen = {**picks, **profile.positions}
        optics = self._config.optics
        positions: dict[DeviceId, AxisPosition] = {}
        for camera, light in profile.lights().items():
            lit, seen = optics.paths_from(light, chosen), optics.paths_to(camera, chosen)
            if not lit or not seen:
                raise ValueError(f"No light reaches '{camera}' with {chosen}.")
            on_paths = {node for path in (*lit, *seen) for node in path.nodes}
            positions.update({node: value for node, value in chosen.items() if node in on_paths})
        return positions

    def _sweep_speed(self, profile: SPIMProfile, profile_id: ProfileId) -> float | None:
        """The stage speed of a sweep, in µm/s: 1 spacing in each frame, slower by the scan's margin. The longest
        timeline of the profile sets the frame time, since each frame plays 1 cycle of every generator. A step has no
        speed."""
        scan = self._config.scan
        if scan.motion == "step":
            return None
        if not profile.timelines:
            raise ValueError(f"Profile '{profile_id}' has no timeline, so a sweep has no frame time.")
        frame_time = max(float(timeline.duration) for timeline in profile.timelines.values())
        return profile.spacing / frame_time * (1 - float(scan.margin or 0))

    def _tile_positions(
        self, region: Region, task: TaskDefaults, tile: Mapping[SpecimenAxis, Span]
    ) -> list[dict[SpecimenAxis, float]]:
        """The stage position on each tiled axis of every stop, in the order they run. ``tile`` is what every camera
        sees around the stage position. Tiles overlap by the task's overlap, and the ones that miss the region are left
        out."""
        tiled = self._config.scan.tiled()
        outline = region.outline
        if isinstance(outline, ExplicitPoints):
            centers: list[dict[SpecimenAxis, float]] = [
                {axis: point[axis] for axis in tiled} for point in outline.points
            ]
        elif isinstance(task.path.tiles, Grid):
            lines: dict[SpecimenAxis, list[float]] = {
                axis: self._line(region.extent(axis), tile[axis].length, float(task.overlap[axis])) for axis in tiled
            }
            centers = self._grid(lines, task.path.tiles)
        else:
            raise NotImplementedError(f"tile order '{task.path.tiles.kind}' is not planned yet")
        positions: list[dict[SpecimenAxis, float]] = []
        for center in centers:
            stage: dict[SpecimenAxis, float] = {axis: center[axis] - tile[axis].middle for axis in tiled}
            box: dict[SpecimenAxis, Span] = {
                axis: Span(stage[axis] + tile[axis].low, stage[axis] + tile[axis].high) for axis in tiled
            }
            if region.meets(box):
                positions.append(stage)
        return positions

    @staticmethod
    def _shared(frames: Iterable[Transform], axes: Sequence[SpecimenAxis]) -> dict[SpecimenAxis, Span]:
        """The span on each of ``axes`` that every frame sees. Raise ``ValueError`` when they share none."""
        bounds = [frame.bounds() for frame in frames]
        shared: dict[SpecimenAxis, Span] = {
            axis: Span(max(b[axis].low for b in bounds), min(b[axis].high for b in bounds)) for axis in axes
        }
        if empty := [axis for axis, span in shared.items() if span.length <= 0]:
            raise ValueError(f"The cameras of this task see no common area on {' and '.join(empty)}.")
        return shared

    @staticmethod
    def _overlap(footprint: Footprint, values: Mapping[SpecimenAxis, list[float]]) -> dict[SpecimenAxis, float]:
        """How much of ``footprint`` the nearest neighboring stop sees again on each tiled axis, as a fraction. It is
        below 0 when there is a gap."""
        bounds = footprint.frame.bounds()
        overlap: dict[SpecimenAxis, float] = {}
        for axis, line in values.items():
            if len(line) > 1:
                gap = min(b - a for a, b in itertools.pairwise(line))
                overlap[axis] = round(1 - gap / bounds[axis].length, 4)
        return overlap

    @staticmethod
    def _binning(props: Mapping[str, object]) -> int:
        value = props.get("binning", 1)
        if not isinstance(value, int):
            raise TypeError(f"binning must be a whole number, got {value!r}")
        return value

    @staticmethod
    def _line(extent: Span, length: float, overlap: float) -> list[float]:
        """The centers of tiles of ``length`` along 1 axis that overlap by ``overlap`` and cover ``extent``, centered
        on it."""
        step = length * (1 - overlap)
        count = max(1, math.ceil((extent.length - length) / step - _COUNT_TOLERANCE) + 1)
        first = extent.middle - step * (count - 1) / 2
        return [first + i * step for i in range(count)]

    @staticmethod
    def _grid(lines: Mapping[SpecimenAxis, list[float]], grid: Grid) -> list[dict[SpecimenAxis, float]]:
        """Every combination of the centers on each axis, fastest axis first, each axis from the end the grid starts it
        at. An ``alternate`` axis turns back each time a slower axis moves on."""
        paths = {axis: path for entry in grid.axes for axis, path in entry.items()}
        tiles: list[dict[SpecimenAxis, float]] = [{}]
        for axis in reversed(grid.axis_order):
            first = lines[axis][::-1] if grid.start.get(axis) == "high" else lines[axis]
            grown: list[dict[SpecimenAxis, float]] = []
            for index, tile in enumerate(tiles):
                values = first[::-1] if paths[axis] == "alternate" and index % 2 else first
                for value in values:
                    grown.append({**tile, axis: value})
            tiles = grown
        return tiles


__all__ = [
    "Footprint",
    "FootprintId",
    "PlannedScan",
    "PlannedTask",
    "Planner",
    "TaskPlans",
    "Unplanned",
    "Volume",
    "Zone",
]
