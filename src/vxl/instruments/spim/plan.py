"""The plan of a task: its volumes in the order they run, each with the light path and device positions of its
profile at its tile."""

import math
from collections.abc import Mapping
from dataclasses import dataclass

from vxlib.vector import Span, Vec3D

from vxl.core.instrument.config import AxisPosition, DeviceUid, SpecimenAxis, Stage
from vxl.devices.camera import CameraSensor

from .config import Profile, ProfileId, Scan, SPIMConfig
from .geometry import AxisRun, Transform, footprint, frame_transform
from .state import SPIMState
from .task import ExplicitPoints, Grid, Region, Task, TaskDefaults, TaskId

_COUNT_TOLERANCE = 1e-9


@dataclass(frozen=True)
class Volume:
    """1 profile at 1 tile: the unit that runs, saved as 1 dataset for each camera. The stage starts at ``start`` and
    moves by ``scan``; ``positions`` are set before the scan runs; ``transforms`` give where each camera's pixels
    land."""

    task: TaskId
    profile: ProfileId
    start: Vec3D
    scan: AxisRun
    positions: Mapping[DeviceUid, AxisPosition]
    transforms: Mapping[DeviceUid, Transform]


def plan_task(
    task: Task,
    config: SPIMConfig,
    state: SPIMState,
    sensors: Mapping[DeviceUid, CameraSensor],
) -> list[Volume]:
    """The volumes of 1 task, in the order they run. ``state`` is the instrument's state or its defaults. The open
    devices give ``sensors``. The smallest area that the task's profiles see sets the tile, with the devices set as
    at the middle of the region."""
    region, scan = task.region, config.scan

    middle = state.positions_at({axis: region.extent(axis).middle for axis in Stage.axes()}, {})
    seen = [footprint(_light(config, state.profiles[p], middle, sensors)[1]) for p in task.profiles]
    tile: dict[SpecimenAxis, Span] = {
        axis: min((s[axis] for s in seen), key=lambda s: s.length) for axis in Stage.axes()
    }

    span = _scan_span(region, scan, tile)
    stops: list[tuple[dict[SpecimenAxis, float], dict[DeviceUid, AxisPosition]]] = []
    previous: dict[DeviceUid, AxisPosition] = {}
    for stage in _tile_positions(region, scan, task, tile):
        previous = state.positions_at({**stage, scan.axis: span.middle}, previous)
        stops.append((stage, previous))

    def volume(stage: Mapping[SpecimenAxis, float], picks: Mapping[str, AxisPosition], profile_id: ProfileId) -> Volume:
        """1 profile at 1 stop. ``stage`` is the stop's position on the tiled axes."""
        profile = state.profiles[profile_id]
        positions, frames = _light(config, profile, picks, sensors)
        count = math.floor(span.length / profile.spacing + _COUNT_TOLERANCE) + 1
        run = AxisRun(scan.axis, span.low, profile.spacing, count)
        at = {**stage, scan.axis: span.low}
        start = Vec3D(z=at["z"], y=at["y"], x=at["x"])
        transforms = {camera: frame.scanned(start, run) for camera, frame in frames.items()}
        return Volume(task.id, profile_id, start, run, positions, transforms)

    if task.iteration == "position_major":
        return [volume(stage, picks, profile) for stage, picks in stops for profile in task.profiles]
    return [volume(stage, picks, profile) for profile in task.profiles for stage, picks in stops]


def _light(
    config: SPIMConfig,
    profile: Profile,
    picks: Mapping[str, AxisPosition],
    sensors: Mapping[DeviceUid, CameraSensor],
) -> tuple[dict[DeviceUid, AxisPosition], dict[DeviceUid, Transform]]:
    """What 1 profile needs with the instrument's devices at ``picks``: the positions to set, and each camera's
    frame at stage position 0. Raise ``ValueError`` when a camera gets no light, or the paths from the sample to it
    do not agree on 1 magnification."""
    chosen = {**picks, **profile.positions}
    detectors = config.optics.detectors()
    positions: dict[DeviceUid, AxisPosition] = {}
    frames: dict[DeviceUid, Transform] = {}
    for camera, channel in profile.channels.items():
        lit = config.illumination_paths(channel.illumination, chosen)
        seen = config.detection_paths(camera, chosen)
        if not lit or not seen:
            raise ValueError(f"No light reaches '{camera}' with {chosen}.")
        found = {path.magnification for path in seen}
        magnification = found.pop() if len(found) == 1 else None
        if magnification is None:
            raise ValueError(f"The light paths from the sample to '{camera}' do not give 1 magnification.")
        on_paths = {node for path in (*lit, *seen) for node in path.nodes}
        positions.update({node: value for node, value in chosen.items() if node in on_paths})
        frames[camera] = frame_transform(
            detectors[camera],
            sensors[camera],
            channel.fov,
            binning=_binning(profile.props.get(camera, {})),
            magnification=magnification,
        )
    return positions, frames


def _binning(props: Mapping[str, object]) -> int:
    value = props.get("binning", 1)
    if not isinstance(value, int):
        raise TypeError(f"binning must be a whole number, got {value!r}")
    return value


def _scan_span(region: Region, scan: Scan, tile: Mapping[SpecimenAxis, Span]) -> Span:
    """The stage positions that every capture runs between on the scan axis. Each frame sees ``tile`` around the
    stage position; a slanted frame sees part of the scan axis too. To see both ends of the region at every depth,
    a capture starts at the region's start minus the far edge, and ends at its end minus the near edge."""
    extent, seen = region.extent(scan.axis), tile[scan.axis]
    return Span(extent.low - seen.high, extent.high - seen.low)


def _tile_positions(
    region: Region, scan: Scan, task: TaskDefaults, tile: Mapping[SpecimenAxis, Span]
) -> list[dict[SpecimenAxis, float]]:
    """The stage position on each tiled axis of every stop, in the order they run. ``tile`` is what the cameras see
    around the stage position. Tiles overlap by the task's overlap, and the ones that miss the region are left out."""
    tiled = scan.tiled()
    outline = region.outline
    if isinstance(outline, ExplicitPoints):
        centers: list[dict[SpecimenAxis, float]] = [{axis: point[axis] for axis in tiled} for point in outline.points]
    elif isinstance(task.path.tiles, Grid):
        lines: dict[SpecimenAxis, list[float]] = {
            axis: _line(region.extent(axis), tile[axis].length, float(task.overlap[axis])) for axis in tiled
        }
        centers = _grid(lines, task.path.tiles)
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


def _line(extent: Span, length: float, overlap: float) -> list[float]:
    """The centers of tiles of ``length`` along 1 axis that overlap by ``overlap`` and cover ``extent``, centered on
    it."""
    step = length * (1 - overlap)
    count = max(1, math.ceil((extent.length - length) / step - _COUNT_TOLERANCE) + 1)
    first = extent.middle - step * (count - 1) / 2
    return [first + i * step for i in range(count)]


def _grid(lines: Mapping[SpecimenAxis, list[float]], grid: Grid) -> list[dict[SpecimenAxis, float]]:
    """Every combination of the centers on each axis, fastest axis first. An ``alternate`` axis turns back each time
    a slower axis moves on."""
    paths = {axis: path for entry in grid.axes for axis, path in entry.items()}
    tiles: list[dict[SpecimenAxis, float]] = [{}]
    for axis in reversed(grid.axis_order):
        grown: list[dict[SpecimenAxis, float]] = []
        for index, tile in enumerate(tiles):
            values = lines[axis][::-1] if paths[axis] == "alternate" and index % 2 else lines[axis]
            for value in values:
                grown.append({**tile, axis: value})
        tiles = grown
    return tiles


__all__ = ["Volume", "plan_task"]
