"""Pure spatial resolution for persisted acquisition task definitions."""

import math
from collections.abc import Iterable
from typing import Self

from pydantic import model_validator
from vxlib.schema import FrozenModel

from .config import ExplicitPositions, Point2D, TaskLayout, TiledArea, TileOrder, ZDefinition, ZRange
from .traversal import order_positions


class Bounds(FrozenModel):
    """Axis-aligned bounds relative to a task's stage position, in micrometres."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @classmethod
    def envelope(cls, bounds: Iterable[Self]) -> Self | None:
        values = list(bounds)
        if not values:
            return None
        return cls(
            min_x=min(bound.min_x for bound in values),
            min_y=min(bound.min_y for bound in values),
            max_x=max(bound.max_x for bound in values),
            max_y=max(bound.max_y for bound in values),
        )

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.max_x <= self.min_x or self.max_y <= self.min_y:
            raise ValueError("bounds must have positive width and height")
        return self


def resolve_z(definition: ZDefinition, _xy: Point2D) -> ZRange:
    """Resolve a task's Z definition at one XY position."""

    return definition


def resolve_layout(layout: TaskLayout, *, width: float, height: float, traversal: TileOrder) -> list[Point2D]:
    """Resolve and spatially order the XY positions described by a task layout."""

    match layout:
        case ExplicitPositions(points=points):
            positions = list(points)
        case TiledArea() if width > 0 and height > 0:
            positions = _area_positions(layout, width=width, height=height)
        case TiledArea():
            return []
    return order_positions(
        positions,
        traversal,
        row_tolerance=height * 0.3,
        column_tolerance=width * 0.3,
    )


def _area_positions(area: TiledArea, *, width: float, height: float) -> list[Point2D]:
    xs = [point.x for point in area.points]
    ys = [point.y for point in area.points]
    step_x = width * (1 - area.grid.overlap)
    step_y = height * (1 - area.grid.overlap)
    start_x = math.floor((min(xs) + width / 2 - area.grid.anchor.x) / step_x)
    end_x = max(start_x, math.ceil((max(xs) - width / 2 - area.grid.anchor.x) / step_x))
    start_y = math.floor((min(ys) + height / 2 - area.grid.anchor.y) / step_y)
    end_y = max(start_y, math.ceil((max(ys) - height / 2 - area.grid.anchor.y) / step_y))
    return [
        Point2D(x=x, y=y)
        for ix in range(start_x, end_x + 1)
        for iy in range(start_y, end_y + 1)
        if _rectangle_intersects_polygon(
            x := area.grid.anchor.x + ix * step_x,
            y := area.grid.anchor.y + iy * step_y,
            width,
            height,
            area.points,
        )
    ]


def _rectangle_intersects_polygon(x: float, y: float, width: float, height: float, polygon: list[Point2D]) -> bool:
    half_width, half_height = width / 2, height / 2
    corners = [
        Point2D(x=x - half_width, y=y - half_height),
        Point2D(x=x + half_width, y=y - half_height),
        Point2D(x=x + half_width, y=y + half_height),
        Point2D(x=x - half_width, y=y + half_height),
    ]
    if any(_point_in_polygon(point, polygon) for point in corners):
        return True
    if any(
        x - half_width <= point.x <= x + half_width and y - half_height <= point.y <= y + half_height
        for point in polygon
    ):
        return True
    rectangle_edges = list(zip(corners, [*corners[1:], corners[0]], strict=True))
    polygon_edges = list(zip(polygon, [*polygon[1:], polygon[0]], strict=True))
    return any(
        _segments_intersect(*rectangle, *boundary) for rectangle in rectangle_edges for boundary in polygon_edges
    )


def _point_in_polygon(point: Point2D, polygon: list[Point2D]) -> bool:
    inside = False
    for first, second in zip(polygon, [*polygon[1:], polygon[0]], strict=True):
        if _on_segment(first, point, second):
            return True
        if (first.y > point.y) != (second.y > point.y):
            crossing_x = first.x + (point.y - first.y) * (second.x - first.x) / (second.y - first.y)
            if point.x < crossing_x:
                inside = not inside
    return inside


def _segments_intersect(a: Point2D, b: Point2D, c: Point2D, d: Point2D) -> bool:
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    if (ab_c > 0) != (ab_d > 0) and (cd_a > 0) != (cd_b > 0):
        return True
    return any(
        cross == 0 and _on_segment(start, point, end)
        for cross, start, point, end in (
            (ab_c, a, c, b),
            (ab_d, a, d, b),
            (cd_a, c, a, d),
            (cd_b, c, b, d),
        )
    )


def _cross(a: Point2D, b: Point2D, c: Point2D) -> float:
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def _on_segment(a: Point2D, point: Point2D, b: Point2D) -> bool:
    return (
        _cross(a, b, point) == 0
        and min(a.x, b.x) <= point.x <= max(a.x, b.x)
        and min(a.y, b.y) <= point.y <= max(a.y, b.y)
    )
