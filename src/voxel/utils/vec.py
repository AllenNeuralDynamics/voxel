from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

type Number = int | float


@dataclass
class Vec2D[T: Number]:
    x: T
    y: T

    def __post_init__(self) -> None:
        for attr in ["x", "y"]:
            if not isinstance(getattr(self, attr), (int, float)):
                raise TypeError(f"Unsupported type for {attr}: {type(getattr(self, attr))}")

    def to_str(self) -> str:
        return f"({self.x}, {self.y})"

    @classmethod
    def from_str(cls, data: str) -> Self:
        split = data.strip(" ()").split(",")
        if any("." in s for s in split):
            x, y = float(split[0]), float(split[1])
        else:
            x, y = int(split[0]), int(split[1])
        return cls(x, y)  # type: ignore

    def __repr__(self) -> str:
        return self.to_str()

    def __hash__(self) -> int:
        return hash((self.x, self.y))

    def __add__(self, other: "Vec2D") -> "Vec2D[T]":
        return Vec2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2D") -> "Vec2D[T]":
        return Vec2D(self.x - other.x, self.y - other.y)

    def __matmul__(self, other: Vec2D) -> float:  # @
        return self.x * other.y - self.y * other.x

    def __truediv__(self, other: T) -> Vec2D[float]:
        return Vec2D(self.x / other, self.y / other)

    def __floordiv__(self, other: T) -> Vec2D[int]:
        return Vec2D(int(self.x // other), int(self.y // other))

    # tuple unpacking
    def __iter__(self) -> Iterator[T]:
        return iter((self.x, self.y))


@dataclass
class Vec3D[T: Number]:
    x: T
    y: T
    z: T

    def __post_init__(self):
        for attr in ["x", "y", "z"]:
            if not isinstance(getattr(self, attr), (int, float)):
                raise TypeError(f"Unsupported type for {attr}: {type(getattr(self, attr))}")

    def to_str(self):
        return f"({self.x}, {self.y}, {self.z})"

    @classmethod
    def from_str(cls, data: str) -> Vec3D:
        split = data.strip(" ()").split(",")
        if any("." in s for s in split):
            x, y, z = float(split[0]), float(split[1]), float(split[2])
        else:
            x, y, z = int(split[0]), int(split[1]), int(split[2])
        return cls(x, y, z)  # type: ignore

    def __iter__(self) -> Iterator[T]:
        return iter((self.x, self.y, self.z))

    def __hash__(self):
        return hash((self.x, self.y, self.z))

    def __add__(self, other: "Vec3D") -> "Vec3D":
        return Vec3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3D") -> "Vec3D":
        return Vec3D(self.x - other.x, self.y - other.y, self.z - other.z)


@dataclass
class Plane:
    min_corner: Vec3D
    size: Vec2D | Vec3D

    @property
    def max_corner(self) -> Vec3D:
        return self.min_corner + Vec3D(self.size.x, self.size.y, 0)

    def __repr__(self) -> str:
        return f"Plane(min_corner={self.min_corner}, size={self.size})"
