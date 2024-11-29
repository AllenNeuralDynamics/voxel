import math
from dataclasses import dataclass
from typing import Any, Optional

from voxel.utils.vec import Vec2D, Vec3D


@dataclass
class FrameStack:
    idx: Vec2D
    pos: Vec3D
    size: Vec3D
    z_step_size: float
    channels: list[str]
    settings: Optional[dict[str, dict[str, Any]]] = None

    @property
    def frame_count(self) -> int:
        return math.ceil(self.size.z / self.z_step_size)

    def to_dict(self) -> dict[str, Any]:
        return {
            "idx": self.idx.to_str(),
            "pos": self.pos.to_str(),
            "size": self.size.to_str(),
            "z_step_size": self.z_step_size,
            "channels": self.channels,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FrameStack":
        return cls(
            idx=Vec2D.from_str(data["idx"]),
            pos=Vec3D.from_str(data["pos"]),
            size=Vec3D.from_str(data["size"]),
            z_step_size=data["z_step_size"],
            channels=data["channels"],
            settings=data.get("settings"),
        )
