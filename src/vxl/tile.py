"""Tile and Stack models for acquisition planning."""

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, computed_field

from vxl.camera.base import CameraBatchResult


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


class StackResult(BaseModel):
    """Result of acquiring a z-stack."""

    tile_id: str
    status: StackStatus
    output_dir: Path
    cameras: dict[str, CameraBatchResult]
    num_frames: int
    started_at: datetime
    completed_at: datetime
    duration_s: float
    error_message: str | None = None
