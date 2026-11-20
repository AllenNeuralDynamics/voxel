"""A task: which part of the sample to image, and how to go through it."""

from collections.abc import Mapping, Sequence
from functools import cached_property
from typing import Annotated, Any, Literal, Self

import numpy as np
from pydantic import Field, field_validator, model_validator
from scipy.spatial import ConvexHull as _Hull
from vxlib.issues import Problems
from vxlib.schema import FrozenModel, repeated
from vxlib.units import Portion
from vxlib.vector import Span

from vxl.instrument.config import Stage
from vxl.instrument.state import Task, TaskFields
from vxl.optics import SpecimenAxis

from .config import SPIMConfig

type Point = dict[SpecimenAxis, Annotated[float, Field(allow_inf_nan=False)]]
"""A point of an outline, in µm: its position on 2 stage axes, such as ``{x: 0, z: 500}``."""


def _axes(points: Sequence[Point]) -> tuple[SpecimenAxis, SpecimenAxis]:
    """The 2 stage axes that every point names, in stage order. Raise ``ValueError`` when the points do not all
    name the same 2 axes."""
    named = {frozenset(point) for point in points}
    if len(named) != 1 or len(axes := next(iter(named))) != 2:
        raise ValueError("every point must name the same 2 stage axes, such as {x: 0, y: 0}")
    found: list[SpecimenAxis] = [axis for axis in Stage.axes() if axis in axes]
    return found[0], found[1]


def _pairs(points: Sequence[Point]) -> list[tuple[float, float]]:
    a, b = _axes(points)
    return [(point[a], point[b]) for point in points]


def _collinear(pairs: list[tuple[float, float]]) -> bool:
    (ax, ay), (bx, by) = pairs[0], pairs[1]
    return all((bx - ax) * (y - ay) == (by - ay) * (x - ax) for x, y in pairs[2:])


def _unique(pairs: list[tuple[float, float]], name: str) -> None:
    if duplicates := repeated(pairs):
        raise ValueError(f"{name} points must be unique (repeated: {duplicates})")


class BoundingBox(FrozenModel):
    """The smallest rectangle that holds the points."""

    kind: Literal["bounding_box"]
    points: list[Point] = Field(min_length=2)

    @model_validator(mode="after")
    def _check(self) -> Self:
        pairs = _pairs(self.points)
        if len({a for a, _ in pairs}) < 2 or len({b for _, b in pairs}) < 2:
            raise ValueError("bounding-box points must span both axes")
        return self


class ConvexHull(FrozenModel):
    """The smallest convex shape that holds the points."""

    kind: Literal["convex_hull"]
    points: list[Point] = Field(min_length=3)

    @model_validator(mode="after")
    def _check(self) -> Self:
        pairs = _pairs(self.points)
        _unique(pairs, "convex-hull")
        if _collinear(pairs):
            raise ValueError("convex-hull points must not all lie on 1 line")
        return self


class ExplicitPoints(FrozenModel):
    """1 capture centered on each point. The points name the tiled axes."""

    kind: Literal["explicit_points"]
    points: list[Point] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _unique(_pairs(self.points), "explicit")
        return self


type Outline = Annotated[BoundingBox | ConvexHull | ExplicitPoints, Field(discriminator="kind")]
"""The outline of the part to image, as drawn in 1 view: on 2 stage axes."""


type _Pair = tuple[float, float]
"""A position on a region's 2 outline axes, in the order of :attr:`Region.across`."""

_EPS = 1e-9


def _clip(polygon: list[_Pair], dim: int, span: Span) -> list[_Pair]:
    """The part of a convex polygon whose coordinate ``dim`` is inside ``span``."""
    for bound, sign in ((span.low, 1.0), (span.high, -1.0)):
        kept: list[_Pair] = []
        for i, p in enumerate(polygon):
            q = polygon[(i + 1) % len(polygon)]
            p_in, q_in = (
                sign * (p[dim] - bound) >= -_EPS,
                sign * (q[dim] - bound) >= -_EPS,
            )
            if p_in:
                kept.append(p)
            if p_in != q_in:
                t = (bound - p[dim]) / (q[dim] - p[dim])
                kept.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
        polygon = kept
        if not polygon:
            break
    return polygon


class Region(FrozenModel):
    """Which part of the sample to image, in µm: an ``outline`` on 2 stage axes, and the span ``bounds`` that it
    covers on the third. Every tile of a task covers the same span on the scan axis."""

    outline: Outline
    bounds: Span

    @property
    def across(self) -> tuple[SpecimenAxis, SpecimenAxis]:
        """The 2 axes of the outline, in stage order."""
        return _axes(self.outline.points)

    @property
    def along(self) -> SpecimenAxis:
        """The axis of the bounds: the one the outline does not name."""
        rest: list[SpecimenAxis] = [axis for axis in Stage.axes() if axis not in self.across]
        return rest[0]

    def extent(self, axis: SpecimenAxis) -> Span:
        """How far the region reaches on ``axis``."""
        if axis == self.along:
            return Span(self.bounds.low, self.bounds.high)
        dim = self.across.index(axis)
        values = [pair[dim] for pair in _pairs(self.outline.points)]
        return Span(min(values), max(values))

    def meets(self, box: Mapping[SpecimenAxis, Span]) -> bool:
        """Whether a box that spans some axes meets the region. Explicit points meet every box, since each tile is
        placed on a point."""
        polygon = self._polygon
        if polygon is None:
            return True
        along = box.get(self.along)
        if along is not None and (along.high < self.bounds.low or along.low > self.bounds.high):
            return False
        for dim, axis in enumerate(self.across):
            if axis in box:
                polygon = _clip(polygon, dim, box[axis])
        return bool(polygon)

    @cached_property
    def _polygon(self) -> list[_Pair] | None:
        """The outline as a convex polygon on :attr:`across`, counterclockwise, or ``None`` for explicit points,
        which are no area."""
        pairs = _pairs(self.outline.points)
        match self.outline:
            case BoundingBox():
                (u0, u1), (v0, v1) = [(min(values), max(values)) for values in zip(*pairs, strict=True)]
                return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            case ConvexHull():
                return [pairs[i] for i in _Hull(np.array(pairs)).vertices]
            case ExplicitPoints():
                return None


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

    def problems(self, config: SPIMConfig) -> Problems:
        """Return each axis here that does not fit the axis that the scan of ``config`` moves and those it tiles."""
        scan = config.scan
        tiled = scan.tiled()
        problems = Problems.assignments(
            expected=tiled,
            assigned=self.overlap,
            code="task.overlap",
            label="tiled-axis overlap",
        ).under("overlap")
        problems += Problems.assignments(
            expected=[scan.axis],
            assigned=self.path.scan,
            code="task.path.scan",
            label="scan-axis path",
        ).under("path", "scan")
        tiles = self.path.tiles
        if isinstance(tiles, Grid):
            if sorted(tiles.axis_order) != sorted(tiled):
                msg = f"The grid must list each tiled axis once: {tiled}."
                problems.add("task.path.grid_axes", msg, "path", "tiles", "axes")
            elif tiles.axes[-1][tiles.axis_order[-1]] == "alternate":
                msg = f"'{tiles.axis_order[-1]}' is the slowest tiled axis, so it never repeats and cannot alternate."
                problems.add(
                    "task.path.slowest_alternate",
                    msg,
                    "path",
                    "tiles",
                    "axes",
                    len(tiles.axes) - 1,
                )
        return problems


class SPIMTask(Task, TaskDefaults):
    """1 entry in the plan of a SPIM instrument, stored complete: the region to image, and how to go through it."""

    region: Region

    @classmethod
    def complete(cls, data: Mapping[str, Any], defaults: TaskDefaults) -> Self:
        """Build a task, taking from ``defaults`` each setting that ``data`` leaves out."""
        filled = defaults.model_dump(mode="json") | dict(data)
        return cls.model_validate(filled)

    def problems(self, config: SPIMConfig) -> Problems:
        """The problems of the defaults, and the region's: each axis it reaches past the stage's ``specimen`` range."""
        problems = super().problems(config)
        scan = config.scan
        for axis in Stage.axes():
            specimen, extent = config.stage.axis(axis).specimen, self.region.extent(axis)
            if specimen is not None and (extent.low < specimen.low or extent.high > specimen.high):
                msg = (
                    f"The region reaches [{extent.low}, {extent.high}] on {axis}, past the specimen range "
                    f"[{specimen.low}, {specimen.high}]."
                )
                problems.add("task.region.outside_specimen", msg, "region")
        if isinstance(self.region.outline, ExplicitPoints) and set(self.region.across) != set(scan.tiled()):
            msg = f"Explicit points place captures on the tiled axes, so they must name {' and '.join(scan.tiled())}."
            problems.add("task.region.explicit_points_untiled", msg, "region", "outline")
        if isinstance(self.path.tiles, AsGiven) and not isinstance(self.region.outline, ExplicitPoints):
            msg = "'as_given' keeps the order of explicit points, and this region has none."
            problems.add("task.path.as_given_needs_points", msg, "path", "tiles")
        return problems


class SPIMTaskFields(TaskFields, total=False):
    """The fields of a :class:`SPIMTask` that an update may change, each one optional."""

    overlap: dict[SpecimenAxis, Portion]
    path: TaskPath
    iteration: Iteration
    region: Region
