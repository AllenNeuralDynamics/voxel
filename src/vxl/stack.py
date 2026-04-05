"""Stack, Tile, ordering, and acquisition result models."""

import math
import secrets
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from ome_zarr_writer.types import Compression, ScaleLevel
from pydantic import BaseModel, Field, computed_field

# ==================== Ordering Algorithms ====================


def _dist(a: "Stack", b: "Stack") -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _band_tolerance(stacks: list["Stack"], axis: str) -> float:
    """Median FOV dimension * 0.3 along the band axis."""
    if not stacks:
        return 1.0
    sizes = sorted(s.h if axis == "y" else s.w for s in stacks)
    return sizes[len(sizes) // 2] * 0.3


def _cluster_bands(stacks: list["Stack"], axis: str) -> list[list["Stack"]]:
    """Group stacks into bands along the given axis by proximity."""
    if not stacks:
        return []
    tol = _band_tolerance(stacks, axis)
    key = (lambda s: s.y) if axis == "y" else (lambda s: s.x)
    ordered = sorted(stacks, key=key)

    bands: list[list[Stack]] = [[ordered[0]]]
    for s in ordered[1:]:
        if abs(key(s) - key(bands[-1][0])) <= tol:
            bands[-1].append(s)
        else:
            bands.append([s])
    return bands


def _sweep(stacks: list["Stack"], *, band_axis: str, sort_axis: str) -> list["Stack"]:
    """Sort into bands, then sort within each band."""
    bands = _cluster_bands(stacks, band_axis)
    sort_key = (lambda s: s.x) if sort_axis == "x" else (lambda s: s.y)
    result: list[Stack] = []
    for band in bands:
        result.extend(sorted(band, key=sort_key))
    return result


def _snake(stacks: list["Stack"], *, band_axis: str, sort_axis: str) -> list["Stack"]:
    """Sort into bands, alternating direction within bands."""
    bands = _cluster_bands(stacks, band_axis)
    sort_key = (lambda s: s.x) if sort_axis == "x" else (lambda s: s.y)
    result: list[Stack] = []
    for i, band in enumerate(bands):
        result.extend(sorted(band, key=sort_key, reverse=(i % 2 == 1)))
    return result


def _nearest_neighbor(stacks: list["Stack"]) -> list["Stack"]:
    """Greedy nearest-neighbor ordering. O(n²)."""
    if len(stacks) <= 1:
        return list(stacks)
    remaining = list(stacks)
    result = [remaining.pop(0)]
    while remaining:
        current = result[-1]
        nearest_idx = min(range(len(remaining)), key=lambda i: _dist(current, remaining[i]))
        result.append(remaining.pop(nearest_idx))
    return result


def _two_opt(path: list["Stack"]) -> list["Stack"]:
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


class StackOrder(StrEnum):
    """Stack acquisition ordering strategy. Callable — sorts a list of stacks."""

    SWEEP_ROW = "sweep_row"
    SWEEP_COLUMN = "sweep_column"
    SNAKE_ROW = "snake_row"
    SNAKE_COLUMN = "snake_column"
    NEAREST_NEIGHBOR = "nearest_neighbor"
    OPTIMIZED = "optimized"
    CUSTOM = "custom"

    def __call__(self, stacks: list["Stack"]) -> list["Stack"]:
        match self:
            case StackOrder.SWEEP_ROW:
                return _sweep(stacks, band_axis="y", sort_axis="x")
            case StackOrder.SWEEP_COLUMN:
                return _sweep(stacks, band_axis="x", sort_axis="y")
            case StackOrder.SNAKE_ROW:
                return _snake(stacks, band_axis="y", sort_axis="x")
            case StackOrder.SNAKE_COLUMN:
                return _snake(stacks, band_axis="x", sort_axis="y")
            case StackOrder.NEAREST_NEIGHBOR:
                return _nearest_neighbor(stacks)
            case StackOrder.OPTIMIZED:
                return _two_opt(_nearest_neighbor(stacks))
            case _:
                return stacks


# ==================== Data Models ====================


class StorageConfig(BaseModel):
    """Settings for how acquired data is stored."""

    store_path: Path = Field(description="Absolute path where acquired zarr data is written")
    max_level: ScaleLevel = Field(default=ScaleLevel.L3, description="Maximum pyramid downscale level")
    compression: Compression = Field(default=Compression.BLOSC_LZ4, description="Compression codec for zarr chunks")
    batch_z_shards: int = Field(default=1, gt=0, description="Number of Z shards per batch")
    target_shard_gb: float = Field(default=1.0, gt=0, description="Target shard size in GB")


class StackStatus(StrEnum):
    PLANNED = "planned"
    COMMITTED = "committed"
    ACQUIRING = "acquiring"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Tile(BaseModel):
    """2D tile position, auto-generated from grid planning.

    All positions and dimensions are in micrometers (µm).
    Positions (x, y) represent the CENTER of the tile.
    Tile bounds extend from (x - w/2, y - h/2) to (x + w/2, y + h/2).
    """

    tile_id: str
    row: int
    col: int
    x: float
    y: float
    w: float  # Full FOV width
    h: float  # Full FOV height


class Stack(BaseModel):
    """3D acquisition unit — a self-contained spatial volume to acquire.

    Positions (x, y) are center-anchored in micrometers (µm).
    Z uses start/end (absolute stage positions) rather than center,
    reflecting the scan direction and starting position.
    """

    stack_id: str = Field(default_factory=lambda: secrets.token_hex(4))
    x: float
    y: float
    w: float  # FOV width at creation (µm)
    h: float  # FOV height at creation (µm)
    z_start: float
    z_end: float
    z_step: float
    profile_id: str
    status: StackStatus = StackStatus.PLANNED
    output_path: str | None = None

    @computed_field
    @property
    def num_frames(self) -> int:
        return int((self.z_end - self.z_start) / self.z_step) + 1


class BatchResult(BaseModel):
    """Result of one capture_batch() call."""

    num_frames: int
    started_at: datetime
    completed_at: datetime
    duration_s: float
    dropped_frames: int = 0


class ChannelResult(BaseModel):
    """Result of a full stack acquisition for one channel."""

    camera_id: str
    batches: list[BatchResult]


class StackResult(BaseModel):
    """Result of acquiring a z-stack."""

    stack_id: str
    status: StackStatus
    output_dir: Path
    channels: dict[str, ChannelResult]
    num_frames: int
    started_at: datetime
    completed_at: datetime
    duration_s: float
    error_message: str | None = None
