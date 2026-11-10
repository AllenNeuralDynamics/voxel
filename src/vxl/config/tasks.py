"""Tasks: which part of the sample to image, with which profiles, and how the axes go."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator
from vxlib.schema import FrozenModel, repeated
from vxlib.units import Portion
from vxlib.vector import Vec2D, Vec3D

from vxl.config.basics import ProfileId, SpecimenAxis, TaskId, Violation, assignment_violations

if TYPE_CHECKING:
    from vxl.instrument_next.engine import Engine


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


class Path(FrozenModel):
    """How the axes go: the axes that move inside each capture, and the tiles between captures."""

    scan: dict[SpecimenAxis, AxisPath]
    tiles: TileOrder


type Iteration = Literal["position_major", "profile_major"]


class TaskSettings(FrozenModel):
    """The settings a task can take from ``config.default.task``. ``overlap`` is per tiled axis."""

    overlap: dict[SpecimenAxis, Portion]
    path: Path
    iteration: Iteration

    def violations(self, engine: "Engine[Any]") -> list[Violation]:
        """Return each axis here that does not fit the axes that ``engine`` moves and those it tiles."""
        axes, tiled = engine.moving_axes(), engine.tiled_axes()
        violations = assignment_violations(
            expected=tiled,
            assigned=self.overlap,
            loc=("overlap",),
            code="task.overlap",
            label="tiled-axis overlap",
        )
        violations += assignment_violations(
            expected=axes,
            assigned=self.path.scan,
            loc=("path", "scan"),
            code="task.path.scan",
            label="moving-axis path",
        )
        violations += [
            Violation(
                code="task.path.scan_one_way",
                msg=f"The engine moves '{axis}' one way only, so it cannot alternate.",
                loc=("path", "scan", axis),
            )
            for axis, way in self.path.scan.items()
            if way == "alternate" and axis in axes and not axes[axis].alternate
        ]
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
    profiles: list[ProfileId] = Field(min_length=1)

    @field_validator("profiles")
    @classmethod
    def _unique_profiles(cls, value: list[str]) -> list[str]:
        if duplicates := repeated(value):
            raise ValueError(f"profiles in a task must be unique (repeated: {duplicates})")
        return value

    @classmethod
    def complete(cls, data: Mapping[str, Any], defaults: TaskSettings) -> Self:
        """Build a task, taking from ``defaults`` each setting that ``data`` leaves out."""
        filled = defaults.model_dump(mode="json") | dict(data)
        return cls.model_validate(filled)

    def violations(self, engine: "Engine[Any]") -> list[Violation]:
        violations = super().violations(engine)
        if isinstance(self.region.xy, ExplicitPoints) and ({"x", "y"} & set(engine.moving_axes())):
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


__all__ = [
    "AsGiven",
    "AxisPath",
    "Bound",
    "BoundingBox",
    "ConvexHull",
    "ExplicitPoints",
    "Grid",
    "Iteration",
    "NearestNeighbor",
    "Optimized",
    "Path",
    "Region",
    "Surface",
    "Task",
    "TaskSettings",
    "TileOrder",
    "XYShape",
    "ZBounds",
]
