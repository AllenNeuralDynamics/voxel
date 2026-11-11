"""Where a task's region is imaged: the position of each tile, and the span each moving axis covers there.

A Z bound is a flat height or a surface of measured heights. Between the measured points, a surface is a flat
plane over each triangle of neighbors (Delaunay); past the outer points, it takes the value at the nearest edge.
"""

import math
from collections.abc import Mapping
from itertools import pairwise

import numpy as np
from scipy.spatial import ConvexHull, Delaunay
from vxlib.vector import Span, Vec2D

from vxl.hal_next.config import SpecimenAxis

from .config import Bound, Region, Surface, ZBounds

type _Point = tuple[float, float]
"""An XY position as ``(x, y)``, for the math inside this module only."""

_EPS = 1e-9


def tile_positions(region: Region, moving: Mapping[SpecimenAxis, object]) -> list[dict[SpecimenAxis, float]]:
    """The tiles of a region in the order they run. A tile is the position, in µm, of each axis that holds still
    during a scan. Stand-in: 1 tile at the middle of the region; no tiling, overlap or order yet."""
    xy = _region_xy(region)
    tile: dict[SpecimenAxis, float] = {axis: xy[axis].middle for axis in ("x", "y") if axis not in moving}
    if "z" not in moving:
        middle = Vec2D(x=xy["x"].middle, y=xy["y"].middle)
        tile["z"] = _capture_z(region.z, low=middle, high=middle).middle
    return [tile]


def tile_spans(
    region: Region,
    tile: Mapping[SpecimenAxis, float],
    moving: Mapping[SpecimenAxis, object],
    footprint: Mapping[SpecimenAxis, Span],
) -> dict[SpecimenAxis, Span]:
    """The span, in µm, each moving axis covers at ``tile``, innermost first. ``footprint`` is the area the cameras
    see around the stage position. A moving X or Y covers the region; a moving Z covers the surface under the
    footprint."""
    xy = _region_xy(region)

    def seen(axis: SpecimenAxis) -> Span:
        if axis in moving:
            return xy[axis]
        return Span(tile[axis] + footprint[axis].low, tile[axis] + footprint[axis].high)

    spans: dict[SpecimenAxis, Span] = {}
    for axis in moving:
        if axis == "z":
            x, y = seen("x"), seen("y")
            spans[axis] = _capture_z(region.z, low=Vec2D(x=x.low, y=y.low), high=Vec2D(x=x.high, y=y.high))
        else:
            spans[axis] = xy[axis]
    return spans


def _region_xy(region: Region) -> dict[SpecimenAxis, Span]:
    points = region.xy.points
    return {
        "x": Span(min(p.x for p in points), max(p.x for p in points)),
        "y": Span(min(p.y for p in points), max(p.y for p in points)),
    }


def _capture_z(z: ZBounds, *, low: Vec2D, high: Vec2D) -> Span:
    """The Z a capture over the XY area from ``low`` to ``high`` must image: the lowest start to the highest end."""
    area = ((low.x, low.y), (high.x, high.y))
    return Span(_extent(z.start, *area).low, _extent(z.end, *area).high)


def _extent(bound: Bound, low: _Point, high: _Point) -> Span:
    if isinstance(bound, Surface):
        return _Interpolation(bound).extent(low, high)
    return Span(bound, bound)


class _Interpolation:
    """A surface's height at any XY position, built once from its measured points."""

    def __init__(self, surface: Surface) -> None:
        self.points: list[_Point] = [(p.x, p.y) for p in surface.points]
        self.z = [p.z for p in surface.points]
        self.triangulation = Delaunay(np.array(self.points))
        self.hull: list[int] = [int(i) for i in ConvexHull(np.array(self.points)).vertices]  # counterclockwise

    def at(self, p: _Point) -> float:
        """The height at an XY position: on the plane of the triangle that holds it, or at the nearest edge point."""
        simplex = int(self.triangulation.find_simplex(np.array(p)))
        if simplex < 0:
            return self._edge_height(p)
        affine = self.triangulation.transform[simplex]
        b0, b1 = affine[:2] @ (np.array(p) - affine[2])
        a, b, c = self.triangulation.simplices[simplex]
        return float(b0 * self.z[a] + b1 * self.z[b] + (1 - b0 - b1) * self.z[c])

    def _edge_height(self, p: _Point) -> float:
        best = (math.inf, 0.0)
        for i, j in pairwise((*self.hull, self.hull[0])):
            t, q = _closest_on_segment(p, self.points[i], self.points[j])
            distance = math.dist(p, q)
            if distance < best[0]:
                best = (distance, self.z[i] + t * (self.z[j] - self.z[i]))
        return best[1]

    def extent(self, low: _Point, high: _Point) -> Span:
        """The lowest and highest height over the box from ``low`` to ``high``, exactly.

        The surface is flat on each triangle, and past the hull it takes its edge's value, so its extremes over a box
        are at the box corners, the measured points inside the box, the places where triangle edges cross the box's
        edges, and the hull corners whose outward region reaches into the box.
        """
        candidates = [self.at((x, y)) for x in (low[0], high[0]) for y in (low[1], high[1])]
        candidates += [z for (px, py), z in zip(self.points, self.z, strict=True) if _inside((px, py), low, high)]
        triangles = self.triangulation.simplices
        edges = {(min(u, v), max(u, v)) for a, b, c in triangles for u, v in ((a, b), (b, c), (c, a))}
        for i, j in edges:
            candidates += [self.at(p) for p in _segment_crossings(self.points[i], self.points[j], low, high)]
        count = len(self.hull)
        for k, v in enumerate(self.hull):
            before, after = self.points[self.hull[k - 1]], self.points[self.hull[(k + 1) % count]]
            if _outward_region_meets(self.points[v], before, after, low, high):
                candidates.append(self.z[v])
        return Span(min(candidates), max(candidates))


def _inside(p: _Point, low: _Point, high: _Point) -> bool:
    return low[0] <= p[0] <= high[0] and low[1] <= p[1] <= high[1]


def _closest_on_segment(p: _Point, a: _Point, b: _Point) -> tuple[float, _Point]:
    """The fraction along ``a``→``b`` of the point nearest ``p``, and that point."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return t, (a[0] + t * dx, a[1] + t * dy)


def _segment_crossings(a: _Point, b: _Point, low: _Point, high: _Point) -> list[_Point]:
    """Where segment ``a``→``b`` crosses the edges of the box from ``low`` to ``high``."""
    found: list[_Point] = []
    for dim, bound in ((0, low[0]), (0, high[0]), (1, low[1]), (1, high[1])):
        da = a[dim] - bound
        db = b[dim] - bound
        if da * db < 0:
            t = da / (da - db)
            p = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            other = 1 - dim
            if low[other] - _EPS <= p[other] <= high[other] + _EPS:
                found.append(p)
    return found


def _ray_meets_box(origin: _Point, direction: _Point, low: _Point, high: _Point) -> bool:
    t_low, t_high = 0.0, math.inf
    for dim in (0, 1):
        if abs(direction[dim]) < _EPS:
            if not low[dim] <= origin[dim] <= high[dim]:
                return False
            continue
        t1 = (low[dim] - origin[dim]) / direction[dim]
        t2 = (high[dim] - origin[dim]) / direction[dim]
        t_low, t_high = max(t_low, min(t1, t2)), min(t_high, max(t1, t2))
    return t_low <= t_high


def _outward_region_meets(v: _Point, before: _Point, after: _Point, low: _Point, high: _Point) -> bool:
    """Whether some point of the box has hull corner ``v`` as its nearest edge point."""

    def in_region(q: _Point) -> bool:
        d = (q[0] - v[0], q[1] - v[1])
        return d[0] * (before[0] - v[0]) + d[1] * (before[1] - v[1]) <= _EPS and (
            d[0] * (after[0] - v[0]) + d[1] * (after[1] - v[1]) <= _EPS
        )

    if any(in_region((x, y)) for x in (low[0], high[0]) for y in (low[1], high[1])) or _inside(v, low, high):
        return True
    normal_before = (v[1] - before[1], before[0] - v[0])
    normal_after = (after[1] - v[1], v[0] - after[0])
    return _ray_meets_box(v, normal_before, low, high) or _ray_meets_box(v, normal_after, low, high)


__all__ = ["tile_positions", "tile_spans"]
