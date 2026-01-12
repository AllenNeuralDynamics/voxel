"""Tile and Stack models for acquisition planning."""

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, computed_field

from spim_rig.camera.base import CameraBatchResult


class StackStatus(StrEnum):
    PLANNED = "planned"
    COMMITTED = "committed"
    ACQUIRING = "acquiring"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Tile(BaseModel):
    """2D tile position, auto-generated from grid planning."""

    tile_id: str
    row: int
    col: int
    x_um: float
    y_um: float
    w_um: float
    h_um: float


class Stack(Tile):
    """3D acquisition unit = Tile + z-range."""

    z_start_um: float
    z_end_um: float
    z_step_um: float
    profile_id: str
    status: StackStatus = StackStatus.PLANNED
    output_path: str | None = None

    @computed_field
    @property
    def num_frames(self) -> int:
        return int((self.z_end_um - self.z_start_um) / self.z_step_um) + 1


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
