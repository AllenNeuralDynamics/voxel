from dataclasses import dataclass
from typing import Union


@dataclass
class Vec2D:
    x: int | float
    y: int | float

    def __post_init__(self):
        for attr in ['x', 'y']:
            if not isinstance(getattr(self, attr), (int, float)):
                raise TypeError(f"Unsupported type for {attr}: {type(getattr(self, attr))}")

    def to_dict(self):
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data):
        return cls(x=data["x"], y=data["y"])

    def __repr__(self):
        return f"({self.x}, {self.y})"

    def __add__(self, other: 'Vec2D') -> 'Vec2D':
        return Vec2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other: 'Vec2D') -> 'Vec2D':
        return Vec2D(self.x - other.x, self.y - other.y)

    def __mul__(self, other):
        if isinstance(other, Vec2D):
            return self.x * other.x + self.y * other.y

        if isinstance(other, (int, float)):
            return Vec2D(self.x * other, self.y * other)

        raise TypeError(f"Unsupported type for multiplication: {type(other)}")

    def __truediv__(self, other):
        return Vec2D(self.x / other, self.y / other)

    def __floordiv__(self, other):
        return Vec2D(self.x // other, self.y // other)


@dataclass
class Vec3D:
    x: float
    y: float
    z: float

    def __post_init__(self):
        for attr in ['x', 'y', 'z']:
            if not isinstance(getattr(self, attr), (int, float)):
                raise TypeError(f"Unsupported type for {attr}: {type(getattr(self, attr))}")

    def to_dict(self):
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, data):
        return cls(x=data["x"], y=data["y"], z=data["z"])

    def __add__(self, other: 'Vec3D') -> 'Vec3D':
        return Vec3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: 'Vec3D') -> 'Vec3D':
        return Vec3D(self.x - other.x, self.y - other.y, self.z - other.z)


@dataclass
class Plane:
    min_corner: Vec3D
    size: Union[Vec2D, Vec3D]

    @property
    def max_corner(self) -> Vec3D:
        return self.min_corner + Vec3D(self.size.x, self.size.y, 0)

    def __repr__(self):
        return f"Plane(min_corner={self.min_corner}, size={self.size})"