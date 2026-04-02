"""Tile, Stack, and acquisition result models."""

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from ome_zarr_writer.types import Compression, ScaleLevel
from pydantic import BaseModel, Field, computed_field


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


class Stack(Tile):
    """3D acquisition unit = Tile + z-range.

    Inherits center-anchored positioning from Tile.
    All positions in micrometers (µm).
    """

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
    """Result of acquiring a z-stack at one tile position."""

    tile_id: str
    status: StackStatus
    output_dir: Path
    channels: dict[str, ChannelResult]
    num_frames: int
    started_at: datetime
    completed_at: datetime
    duration_s: float
    error_message: str | None = None
