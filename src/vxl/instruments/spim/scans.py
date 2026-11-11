"""The scans of a task: 1 profile at 1 tile, how the scan axis runs, and where each camera's pixels land.

Every position is in specimen µm. A stage position is where the center of each camera's sensor is. Array axes are
in z, y, x order, slowest first, as OME-Zarr stores them.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import product

import numpy as np
from rigup.config import DeviceUid
from vxlib.vector import Span, Vec3D

from vxl.devices.camera import CameraSensor
from vxl.hal_next.config import Detector, SpecimenAxis
from vxl.models import AreaROI, AxisPosition

from .config import HALConfig, ProfileId, StageFollowRule, State, Task, TaskId
from .region import tile_positions, tile_spans

_COUNT_TOLERANCE = 1e-9


@dataclass(frozen=True)
class AxisRun:
    """How the scan axis runs during a scan: ``count`` frames, ``spacing`` µm apart, from ``first`` µm."""

    axis: SpecimenAxis
    first: float
    spacing: float
    count: int


@dataclass(frozen=True)
class Scan:
    """1 profile at 1 tile. The stage starts at ``start``; ``positions`` are set before the scan runs; ``transforms``
    give where each camera's pixels land."""

    task: TaskId
    profile: ProfileId
    start: Vec3D
    runs: Sequence[AxisRun]
    positions: Mapping[DeviceUid, AxisPosition]
    transforms: Mapping[DeviceUid, "Transform"]


def plan_task(task: Task, hal: HALConfig, settings: State, sensors: Mapping[DeviceUid, CameraSensor]) -> list[Scan]:
    """The scans of 1 task, in the order they run: each profile at each tile. ``settings`` is the instrument's
    state or the file's ``default``."""
    previous: dict[DeviceUid, AxisPosition] = {}
    scans: list[Scan] = []
    for tile in tile_positions(task.region, {hal.scan.axis: hal.scan.motion}):
        previous = _picks(settings.positions, tile, previous)
        scans += [_scan(task, profile, tile, previous, hal, settings, sensors) for profile in task.profiles]
    return scans


def _picks(
    held: Mapping[DeviceUid, StageFollowRule | AxisPosition],
    tile: Mapping[SpecimenAxis, float],
    previous: Mapping[DeviceUid, AxisPosition],
) -> dict[DeviceUid, AxisPosition]:
    """The position of each device that the instrument sets, at ``tile``. ``previous`` gives the positions at the
    tile before, which a device that follows the stage keeps within its margin."""
    picks: dict[DeviceUid, AxisPosition] = {}
    for device, position in held.items():
        if not isinstance(position, StageFollowRule):
            picks[device] = position
            continue
        if position.axis not in tile:
            raise ValueError(f"'{device}' follows '{position.axis}', which moves during a scan")
        before = previous.get(device)
        picks[device] = position.position(tile[position.axis], previous=before if isinstance(before, str) else None)
    return picks


def _scan(
    task: Task,
    profile_id: ProfileId,
    tile: Mapping[SpecimenAxis, float],
    picks: Mapping[str, AxisPosition],
    hal: HALConfig,
    settings: State,
    sensors: Mapping[DeviceUid, CameraSensor],
) -> Scan:
    """1 profile at 1 tile."""
    profile = settings.profiles[profile_id]
    light = profile.light_setting(hal, picks)
    detectors = hal.optics.detectors()
    frames = {
        camera: frame_transform(
            detectors[camera],
            sensors[camera],
            channel.fov,
            binning=_binning(profile.props.get(camera, {})),
            magnification=light.magnification[camera],
        )
        for camera, channel in profile.channels.items()
    }
    spans = tile_spans(task.region, tile, {hal.scan.axis: hal.scan.motion}, _footprint(frames))
    runs = [
        AxisRun(axis, span.low, profile.spacing, math.floor(span.length / profile.spacing + _COUNT_TOLERANCE) + 1)
        for axis, span in spans.items()
    ]
    at = {**tile, **{run.axis: run.first for run in runs}}
    start = Vec3D(z=at["z"], y=at["y"], x=at["x"])
    return Scan(
        task=task.id,
        profile=profile_id,
        start=start,
        runs=runs,
        positions=light.positions,
        transforms={camera: frame.scanned(start, runs) for camera, frame in frames.items()},
    )


def _footprint(frames: Mapping[DeviceUid, "Transform"]) -> dict[SpecimenAxis, Span]:
    """The span on each axis that some camera sees, around the stage position."""
    seen = [frame.bounds() for frame in frames.values()]
    return {axis: Span(min(s[axis].low for s in seen), max(s[axis].high for s in seen)) for axis in ("z", "y", "x")}


def _binning(props: Mapping[str, object]) -> int:
    value = props.get("binning", 1)
    if not isinstance(value, int):
        raise TypeError(f"binning must be a whole number, got {value!r}")
    return value


_ZERO = Vec3D(z=0.0, y=0.0, x=0.0)


@dataclass(frozen=True)
class Transform:
    """Where each element of an array sits in the specimen. Element ``[i, j, k]`` is at
    ``origin + i * steps[0] + j * steps[1] + k * steps[2]``."""

    origin: Vec3D
    steps: tuple[Vec3D, Vec3D, Vec3D]
    shape: tuple[int, int, int]

    def position(self, index: Sequence[float]) -> Vec3D:
        """The specimen position of an index, 1 value for each array axis."""
        position = self.origin
        for i, step in zip(index, self.steps, strict=True):
            position = position + step * i
        return position

    def bounds(self) -> dict[SpecimenAxis, Span]:
        """The span on each specimen axis that holds every element, out to the outer edges of the first and last."""
        corners = [self.position(c) for c in product(*((-0.5, size - 0.5) for size in self.shape))]
        return {
            axis: Span(min(getattr(c, axis) for c in corners), max(getattr(c, axis) for c in corners))
            for axis in ("z", "y", "x")
        }

    def scanned(self, first: Vec3D, runs: Sequence[AxisRun]) -> "Transform":
        """The transform of 1 capture of frames like this one, taken from stage position ``first``. ``runs`` are
        innermost first; the outermost takes array axis 0, the next axis 1, and so on, each an axis of 1 element."""
        steps, shape = list(self.steps), list(self.shape)
        for i, run in enumerate(reversed(runs)):
            if shape[i] != 1 or steps[i] != _ZERO:
                raise ValueError(f"the frame has no free axis {i} for the run along '{run.axis}'")
            steps[i] = Vec3D(**{axis: run.spacing if axis == run.axis else 0.0 for axis in ("z", "y", "x")})
            shape[i] = run.count
        return Transform(self.origin + first, (steps[0], steps[1], steps[2]), (shape[0], shape[1], shape[2]))

    @property
    def matrix(self) -> np.ndarray:
        """The same as a 4 by 4 affine matrix, the form BigStitcher and OME-Zarr use. Its rows are z, y, x, then
        [0, 0, 0, 1]; its columns are the 3 steps, then the origin."""
        matrix = np.eye(4)
        matrix[:3, :] = np.column_stack([list(v) for v in (*self.steps, self.origin)])
        return matrix


def frame_transform(
    detector: Detector, sensor: CameraSensor, roi: AreaROI, *, binning: int, magnification: float
) -> Transform:
    """The transform of 1 saved frame of a camera at stage position 0: an array of shape (1, y, x). ``detector``
    gives the specimen directions of the frame's sides."""
    along_x, along_y = (side / magnification for side in detector.sides())
    pixel, size = sensor.pixel_um, sensor.size_px

    x_step, y_step = along_x * (pixel.x * binning), along_y * (pixel.y * binning)
    nx, ny = roi.w // binning, max(roi.h // binning, 1)
    # How far the read-out region's center sits from the sensor's center.
    center = along_x * ((roi.x + roi.w / 2 - size.x / 2) * pixel.x) + along_y * (
        (roi.y + roi.h / 2 - size.y / 2) * pixel.y
    )
    origin = center - x_step * ((nx - 1) / 2) - y_step * ((ny - 1) / 2)
    return Transform(origin, (_ZERO, y_step, x_step), (1, ny, nx))


__all__ = ["AxisRun", "Scan", "Transform", "frame_transform", "plan_task"]
