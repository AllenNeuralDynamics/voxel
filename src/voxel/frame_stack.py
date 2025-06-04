import math
from pathlib import Path

from pydantic import BaseModel, field_serializer, field_validator

from voxel.utils.vec import Vec2D, Vec3D


class FrameStack(BaseModel):
    # All units are in um
    idx: Vec2D[int]
    pos_um: Vec3D[float]
    size_um: Vec3D[float]
    step_size_um: float

    @property
    def frame_count(self) -> int:
        return math.ceil(self.size_um.z / self.step_size_um)

    @field_validator("idx", "pos_um", "size_um", mode="before")
    def validate_vec(cls, value: str | Vec2D | Vec3D) -> Vec2D | Vec3D:
        if isinstance(value, str):
            return Vec2D.from_str(value) if "x" in value else Vec3D.from_str(value)
        return value

    @field_serializer("idx", "pos_um", "size_um", when_used="json")
    def serialize_vec(self, value: Vec2D | Vec3D) -> str:
        return value.to_str()


class StackAcquisitionConfig(BaseModel):
    """
    Configuration for stack acquisition.
    This class holds the parameters required for configuring the acquisition engine.
    """

    stack: FrameStack
    channel_idx: int
    channel_name: str
    local_path: str | Path
    remote_path: str | Path | None = None
    batch_size: int = 128

    def __post_init__(self) -> None:
        self._frame_ranges = self._get_frame_ranges(self.stack.frame_count)

    @field_validator("local_path", "remote_path", mode="before")
    def validate_path(cls, value: str | Path) -> Path:
        return Path(value) if isinstance(value, str) else value

    @property
    def frame_ranges(self) -> set[tuple[int, int]]:
        """
        Returns a set of tuples representing the frame ranges for each batch.
        Each tuple contains the start and end indices of the frames in that batch.
        """
        return self._frame_ranges

    def _get_frame_ranges(self, frame_count: int) -> set[tuple[int, int]]:
        """Generate frame ranges for batch acquisition."""
        num_batches = math.ceil(frame_count / self.batch_size)
        frame_ranges = set()
        for i in range(num_batches):
            start_idx = i * self.batch_size + 1
            end_idx = min(start_idx + self.batch_size - 1, frame_count)
            frame_ranges.add((start_idx, end_idx))
        return frame_ranges
