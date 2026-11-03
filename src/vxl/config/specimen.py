"""Config facts about specimen space: its axes, the motors that drive them, how each camera sees it, and regions.

Positions and distances in specimen space are in µm everywhere in Voxel, so they are written as bare numbers.
"""

import math
from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Discriminator, Field, Tag, model_validator
from rigup.config import DeviceUid
from vxlib.schema import FrozenModel, repeated, single_key_tag

type SpecimenAxis = Literal["x", "y", "z"]

SPECIMEN_AXES: tuple[SpecimenAxis, ...] = ("x", "y", "z")

_RIGHT_ANGLE_TOLERANCE = math.sin(math.radians(0.1))


def _check_direction[D: Mapping[str, float]](direction: D) -> D:
    if not direction:
        raise ValueError("a direction needs at least 1 axis")
    if not all(math.isfinite(value) for value in direction.values()):
        raise ValueError("direction values must be finite")
    if math.hypot(*direction.values()) == 0:
        raise ValueError("a direction cannot be all zeros")
    return direction


Direction = Annotated[dict[SpecimenAxis, float], AfterValidator(_check_direction)]
"""A direction in specimen axes, such as ``{x: 1, z: 1}``. Only the direction counts, not the length."""


def unit_vector(direction: Mapping[SpecimenAxis, float]) -> tuple[float, float, float]:
    """Return ``direction`` scaled to length 1, as ``(x, y, z)``."""
    x, y, z = (direction.get(axis, 0.0) for axis in SPECIMEN_AXES)
    length = math.hypot(x, y, z)
    return (x / length, y / length, z / length)


class StageAxis(FrozenModel):
    """The motor that drives 1 specimen axis. ``polarity`` is -1 when the motor counts the other way."""

    device: DeviceUid
    polarity: Literal[1, -1]


class Stage(FrozenModel):
    x: StageAxis
    y: StageAxis
    z: StageAxis

    def axes(self) -> dict[SpecimenAxis, StageAxis]:
        return {"x": self.x, "y": self.y, "z": self.z}


class DetectionGeometry(FrozenModel):
    """What geometry reads from a detection path.

    ``width`` and ``height`` are the specimen directions of the camera's x and y pixels, the same 2 sides that
    a profile's ``fov`` counts along. A line camera has only ``width``.
    """

    magnification: float = Field(gt=0, allow_inf_nan=False)
    width: Direction
    height: Direction | None = None

    @model_validator(mode="after")
    def _check_right_angle(self) -> Self:
        if self.height is not None:
            cosine = sum(a * b for a, b in zip(unit_vector(self.width), unit_vector(self.height), strict=True))
            if abs(cosine) > _RIGHT_ANGLE_TOLERANCE:
                angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
                raise ValueError(f"'width' and 'height' must be at 90° to each other (they are at {angle:.2f}°)")
        return self


class Point2D(FrozenModel):
    """An XY position in µm."""

    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class SurfacePoint(FrozenModel):
    """A measured height ``z`` at an XY position, all in µm."""

    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    z: float = Field(allow_inf_nan=False)


def _collinear(points: list[tuple[float, float]]) -> bool:
    (x0, y0), (x1, y1) = points[0], points[1]
    return all((x1 - x0) * (y - y0) == (y1 - y0) * (x - x0) for x, y in points[2:])


def _unique(points: list[tuple[float, float]], name: str) -> None:
    if duplicates := repeated(points):
        raise ValueError(f"{name} points must be unique (repeated: {duplicates})")


class BoundingBox(FrozenModel):
    """The smallest rectangle that holds the points."""

    bounding_box: list[Point2D] = Field(min_length=2)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if len({p.x for p in self.bounding_box}) < 2 or len({p.y for p in self.bounding_box}) < 2:
            raise ValueError("bounding-box points must span a width and a height")
        return self


class ConvexHull(FrozenModel):
    """The smallest convex shape that holds the points."""

    convex_hull: list[Point2D] = Field(min_length=3)

    @model_validator(mode="after")
    def _check(self) -> Self:
        points = [(p.x, p.y) for p in self.convex_hull]
        _unique(points, "convex-hull")
        if _collinear(points):
            raise ValueError("convex-hull points must not all lie on 1 line")
        return self


class ExplicitPoints(FrozenModel):
    """1 capture centered on each point."""

    explicit_points: list[Point2D] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _unique([(p.x, p.y) for p in self.explicit_points], "explicit")
        return self


type XYShape = Annotated[
    Annotated[BoundingBox, Tag("bounding_box")]
    | Annotated[ConvexHull, Tag("convex_hull")]
    | Annotated[ExplicitPoints, Tag("explicit_points")],
    Discriminator(
        single_key_tag,
        custom_error_type="one_key",
        custom_error_message="write exactly 1 of: 'bounding_box', 'convex_hull', 'explicit_points'",
    ),
]


class Surface(FrozenModel):
    """Measured heights. Between them, flat planes over triangles of neighbors; past the outer points, the edge."""

    points: list[SurfacePoint] = Field(min_length=3)

    @model_validator(mode="after")
    def _check(self) -> Self:
        points = [(p.x, p.y) for p in self.points]
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


__all__ = [
    "SPECIMEN_AXES",
    "Bound",
    "BoundingBox",
    "ConvexHull",
    "DetectionGeometry",
    "Direction",
    "ExplicitPoints",
    "Point2D",
    "Region",
    "SpecimenAxis",
    "Stage",
    "StageAxis",
    "Surface",
    "SurfacePoint",
    "XYShape",
    "ZBounds",
    "unit_vector",
]
