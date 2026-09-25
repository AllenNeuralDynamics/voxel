"""Spatial ordering algorithms for planned acquisition positions."""

import math

from .config import Point2D, TileOrder


def order_positions(
    positions: list[Point2D],
    order: TileOrder,
    *,
    row_tolerance: float,
    column_tolerance: float,
) -> list[Point2D]:
    """Return positions in the requested traversal order."""

    match order:
        case TileOrder.SWEEP_ROW:
            return _sweep(positions, band_axis="y", sort_axis="x", tolerance=row_tolerance)
        case TileOrder.SWEEP_COLUMN:
            return _sweep(positions, band_axis="x", sort_axis="y", tolerance=column_tolerance)
        case TileOrder.SNAKE_ROW:
            return _snake(positions, band_axis="y", sort_axis="x", tolerance=row_tolerance)
        case TileOrder.SNAKE_COLUMN:
            return _snake(positions, band_axis="x", sort_axis="y", tolerance=column_tolerance)
        case TileOrder.NEAREST_NEIGHBOR:
            return _nearest_neighbor(positions)
        case TileOrder.OPTIMIZED:
            return _two_opt(_nearest_neighbor(positions))
        case _:
            return list(positions)


def _dist(a: Point2D, b: Point2D) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _cluster_bands(positions: list[Point2D], axis: str, tolerance: float) -> list[list[Point2D]]:
    """Group tiles into bands along the given axis by proximity."""
    if not positions:
        return []
    key = (lambda point: point.y) if axis == "y" else (lambda point: point.x)
    ordered = sorted(positions, key=key)

    bands = [[ordered[0]]]
    for position in ordered[1:]:
        if abs(key(position) - key(bands[-1][0])) <= tolerance:
            bands[-1].append(position)
        else:
            bands.append([position])
    return bands


def _sweep(positions: list[Point2D], *, band_axis: str, sort_axis: str, tolerance: float) -> list[Point2D]:
    """Sort into bands, then sort within each band."""
    bands = _cluster_bands(positions, band_axis, tolerance)
    sort_key = (lambda point: point.x) if sort_axis == "x" else (lambda point: point.y)
    result: list[Point2D] = []
    for band in bands:
        result.extend(sorted(band, key=sort_key))
    return result


def _snake(positions: list[Point2D], *, band_axis: str, sort_axis: str, tolerance: float) -> list[Point2D]:
    """Sort into bands, alternating direction within bands."""
    bands = _cluster_bands(positions, band_axis, tolerance)
    sort_key = (lambda point: point.x) if sort_axis == "x" else (lambda point: point.y)
    result: list[Point2D] = []
    for i, band in enumerate(bands):
        result.extend(sorted(band, key=sort_key, reverse=(i % 2 == 1)))
    return result


def _nearest_neighbor(positions: list[Point2D]) -> list[Point2D]:
    """Greedy nearest-neighbor ordering. O(n²)."""
    if len(positions) <= 1:
        return list(positions)
    remaining = list(positions)
    result = [remaining.pop(0)]
    while remaining:
        current = result[-1]
        nearest_idx = min(range(len(remaining)), key=lambda i: _dist(current, remaining[i]))
        result.append(remaining.pop(nearest_idx))
    return result


def _two_opt(path: list[Point2D]) -> list[Point2D]:
    """Improve path by reversing segments that reduce total distance."""
    if len(path) <= 3:
        return path
    path = list(path)
    improved = True
    while improved:
        improved = False
        for i in range(len(path) - 2):
            for j in range(i + 2, len(path)):
                d_old = _dist(path[i], path[i + 1])
                d_new = _dist(path[i], path[j])
                if j + 1 < len(path):
                    d_old += _dist(path[j], path[j + 1])
                    d_new += _dist(path[i + 1], path[j + 1])
                if d_new < d_old:
                    path[i + 1 : j + 1] = reversed(path[i + 1 : j + 1])
                    improved = True
    return path
