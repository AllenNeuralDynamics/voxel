"""Tile ordering and acquisition result models."""

import math
from enum import StrEnum

from pydantic import BaseModel


class Tile(BaseModel):
    x: float
    y: float
    w: float  # FOV width at creation (µm)
    h: float  # FOV height at creation (µm)


class TileOrder(StrEnum):
    """Task acquisition ordering strategy. Callable — sorts a list of tiles."""

    SWEEP_ROW = "sweep_row"
    SWEEP_COLUMN = "sweep_column"
    SNAKE_ROW = "snake_row"
    SNAKE_COLUMN = "snake_column"
    NEAREST_NEIGHBOR = "nearest_neighbor"
    OPTIMIZED = "optimized"
    CUSTOM = "custom"

    def __call__[T: Tile](self, tiles: list[T]) -> list[T]:
        match self:
            case TileOrder.SWEEP_ROW:
                return _sweep(tiles, band_axis="y", sort_axis="x")
            case TileOrder.SWEEP_COLUMN:
                return _sweep(tiles, band_axis="x", sort_axis="y")
            case TileOrder.SNAKE_ROW:
                return _snake(tiles, band_axis="y", sort_axis="x")
            case TileOrder.SNAKE_COLUMN:
                return _snake(tiles, band_axis="x", sort_axis="y")
            case TileOrder.NEAREST_NEIGHBOR:
                return _nearest_neighbor(tiles)
            case TileOrder.OPTIMIZED:
                return _two_opt(_nearest_neighbor(tiles))
            case _:
                return tiles


def _dist(a: Tile, b: Tile) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _band_tolerance[T: Tile](tiles: list[T], axis: str) -> float:
    """Median FOV dimension * 0.3 along the band axis."""
    if not tiles:
        return 1.0
    sizes = sorted(s.h if axis == "y" else s.w for s in tiles)
    return sizes[len(sizes) // 2] * 0.3


def _cluster_bands[T: Tile](tiles: list[T], axis: str) -> list[list[T]]:
    """Group tiles into bands along the given axis by proximity."""
    if not tiles:
        return []
    tol = _band_tolerance(tiles, axis)
    key = (lambda s: s.y) if axis == "y" else (lambda s: s.x)
    ordered = sorted(tiles, key=key)

    bands: list[list[T]] = [[ordered[0]]]
    for s in ordered[1:]:
        if abs(key(s) - key(bands[-1][0])) <= tol:
            bands[-1].append(s)
        else:
            bands.append([s])
    return bands


def _sweep[T: Tile](tiles: list[T], *, band_axis: str, sort_axis: str) -> list[T]:
    """Sort into bands, then sort within each band."""
    bands = _cluster_bands(tiles, band_axis)
    sort_key = (lambda s: s.x) if sort_axis == "x" else (lambda s: s.y)
    result: list[T] = []
    for band in bands:
        result.extend(sorted(band, key=sort_key))
    return result


def _snake[T: Tile](tiles: list[T], *, band_axis: str, sort_axis: str) -> list[T]:
    """Sort into bands, alternating direction within bands."""
    bands = _cluster_bands(tiles, band_axis)
    sort_key = (lambda s: s.x) if sort_axis == "x" else (lambda s: s.y)
    result: list[T] = []
    for i, band in enumerate(bands):
        result.extend(sorted(band, key=sort_key, reverse=(i % 2 == 1)))
    return result


def _nearest_neighbor[T: Tile](tiles: list[T]) -> list[T]:
    """Greedy nearest-neighbor ordering. O(n²)."""
    if len(tiles) <= 1:
        return list(tiles)
    remaining = list(tiles)
    result = [remaining.pop(0)]
    while remaining:
        current = result[-1]
        nearest_idx = min(range(len(remaining)), key=lambda i: _dist(current, remaining[i]))
        result.append(remaining.pop(nearest_idx))
    return result


def _two_opt[T: Tile](path: list[T]) -> list[T]:
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
