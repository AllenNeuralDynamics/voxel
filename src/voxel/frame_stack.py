import json
import math
from dataclasses import dataclass
from typing import Any

from voxel.utils.vec import Vec2D, Vec3D


@dataclass
class FrameStack:
    # All units are in um
    idx: Vec2D[int]
    pos_um: Vec3D[float]
    size_um: Vec3D[float]
    step_size_um: float
    settings: dict[str, dict[str, Any]] | None = None

    @property
    def frame_count(self) -> int:
        return math.ceil(self.size_um.z / self.step_size_um)

    def to_dict(self) -> dict[str, Any]:
        return {
            "idx": self.idx.to_str(),
            "pos_um": self.pos_um.to_str(),
            "size_um": self.size_um.to_str(),
            "step_size_um": self.step_size_um,
            "frame_count": self.frame_count,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FrameStack":
        return cls(
            idx=Vec2D.from_str(data["idx"]),
            pos_um=Vec3D.from_str(data["pos_um"]),
            size_um=Vec3D.from_str(data["size_um"]),
            step_size_um=data["step_size_um"],
            settings=data.get("settings"),
        )

    def __str__(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
