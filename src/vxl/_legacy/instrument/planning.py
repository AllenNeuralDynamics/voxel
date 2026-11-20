"""Pure spatial resolution for persisted acquisition task definitions."""

import math

from .config import (
    Bounds,
    Point2D,
    TileOrder,
    XYDefinition,
    XYMode,
    ZDefinition,
    ZRange,
)
from .traversal import order_positions


def resolve_z(definition: ZDefinition, _xy: Point2D) -> ZRange:
    """Resolve a task's Z definition at one XY position."""

    return definition


def resolve_xy(definition: XYDefinition, *, width: float, height: float, traversal: TileOrder) -> list[Point2D]:
    """Resolve and spatially order the positions described by an XY definition."""

    if definition.mode is XYMode.EXPLICIT_POINTS:
        positions = list(definition.points)
    elif width > 0 and height > 0:
        positions = _region_positions(definition, width=width, height=height)
    else:
        return []
    return order_positions(
        positions,
        traversal,
        row_tolerance=height * 0.3,
        column_tolerance=width * 0.3,
    )


def _region_positions(definition: XYDefinition, *, width: float, height: float) -> list[Point2D]:
    bounds = Bounds(
        min=Point2D(x=min(point.x for point in definition.points), y=min(point.y for point in definition.points)),
        max=Point2D(x=max(point.x for point in definition.points), y=max(point.y for point in definition.points)),
    )
    polygon = (
        [
            bounds.min,
            Point2D(x=bounds.max.x, y=bounds.min.y),
            bounds.max,
            Point2D(x=bounds.min.x, y=bounds.max.y),
        ]
        if definition.mode is XYMode.BOUNDING_BOX
        else _convex_hull(definition.points)
    )
    step_x = width * (1 - definition.overlap.x)
    step_y = height * (1 - definition.overlap.y)
    end_x = max(0, math.ceil((bounds.max.x - bounds.min.x - width) / step_x))
    end_y = max(0, math.ceil((bounds.max.y - bounds.min.y - height) / step_y))
    return [
        Point2D(x=x, y=y)
        for ix in range(end_x + 1)
        for iy in range(end_y + 1)
        if _rectangle_intersects_polygon(
            x := bounds.min.x + width / 2 + ix * step_x,
            y := bounds.min.y + height / 2 + iy * step_y,
            width,
            height,
            polygon,
        )
    ]


def _convex_hull(points: list[Point2D]) -> list[Point2D]:
    """Return the outer points in counter-clockwise order."""

    ordered = sorted(points, key=lambda point: (point.x, point.y))

    def cross(origin: Point2D, first: Point2D, second: Point2D) -> float:
        return (first.x - origin.x) * (second.y - origin.y) - (first.y - origin.y) * (second.x - origin.x)

    lower: list[Point2D] = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[Point2D] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return [*lower[:-1], *upper[:-1]]


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
