import math

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

    @field_validator('idx', 'pos_um', 'size_um', mode='before')
    @classmethod
    def validate_vec(cls, value: str | Vec2D | Vec3D) -> Vec2D | Vec3D:
        if isinstance(value, str):
            return Vec2D.from_str(value) if 'x' in value else Vec3D.from_str(value)
        return value

    @field_serializer('idx', 'pos_um', 'size_um', when_used='json')
    def serialize_vec(self, value: Vec2D | Vec3D) -> str:
        return value.to_str()
