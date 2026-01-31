"""Vector types for 2D and 3D coordinates.

Provides float, integer, and positive-validated variants:
- Vec2D, Vec3D: Float vectors for physical coordinates (micrometers, etc.)
- IVec2D, IVec3D: Integer vectors for pixel coordinates, shapes, etc.
- UVec2D, UVec3D: Positive float vectors (all components > 0)
- UIVec2D, UIVec3D: Positive integer vectors (all components > 0)

All vectors use y,x (and z,y,x) ordering to match NumPy array indexing.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Self, final

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

# === 2D Vectors ===


@dataclass(frozen=True, slots=True)
class Vec2D:
    """Float 2D vector with y,x components.

    Use for physical coordinates, scales, field of view, pixel sizes (in micrometers), etc.

    Examples:
        pixel_pitch = Vec2D(y=6.5, x=6.5)  # micrometers
        fov = Vec2D(y=1000.0, x=1500.0)    # micrometers
    """

    y: float
    x: float

    def __iter__(self) -> Iterator[float]:
        yield self.y
        yield self.x

    def __add__(self, other: Self) -> Self:
        return type(self)(self.y + other.y, self.x + other.x)

    def __sub__(self, other: Self) -> Self:
        return type(self)(self.y - other.y, self.x - other.x)

    def __mul__(self, scalar: float) -> Self:
        return type(self)(self.y * scalar, self.x * scalar)

    def __truediv__(self, scalar: float) -> Self:
        return type(self)(self.y / scalar, self.x / scalar)

    def __floordiv__(self, scalar: float) -> Self:
        return type(self)(self.y // scalar, self.x // scalar)

    def __neg__(self) -> Self:
        return type(self)(-self.y, -self.x)

    def to_str(self) -> str:
        """Serialize to 'y,x' string."""
        return f"{self.y},{self.x}"

    @classmethod
    def from_str(cls, s: str) -> Self:
        """Parse from 'y,x' string."""
        parts = s.split(",")
        if len(parts) != 2:
            raise ValueError(f"Expected 'y,x' format, got '{s}'")
        return cls(float(parts[0]), float(parts[1]))

    @classmethod
    def parse(cls, v: "list[float] | tuple[float, float] | dict[str, float] | str") -> Self:
        """Parse from various formats: [y, x], (y, x), {'y': ..., 'x': ...}, or 'y,x' string."""
        if isinstance(v, str):
            return cls.from_str(v)
        if isinstance(v, dict):
            return cls(y=float(v["y"]), x=float(v["x"]))
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return cls(y=float(v[0]), x=float(v[1]))
        raise ValueError(f"Cannot parse {type(v).__name__} as {cls.__name__}")

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {"y": self.y, "x": self.x}

    def to_int(self) -> "IVec2D":
        """Convert to integer vector (truncates toward zero)."""
        return IVec2D(int(self.y), int(self.x))

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.union_schema(
            [
                core_schema.is_instance_schema(cls),
                core_schema.no_info_plain_validator_function(cls.parse),
            ],
            serialization=core_schema.plain_serializer_function_ser_schema(lambda v: v.to_str()),
        )


@dataclass(frozen=True, slots=True)
class IVec2D:
    """Integer 2D vector with y,x components.

    Use for pixel coordinates, sensor sizes, ROI dimensions, array shapes, etc.

    Examples:
        sensor_size = IVec2D(y=10640, x=14192)  # pixels
        roi_offset = IVec2D(y=100, x=200)       # pixels
    """

    y: int
    x: int

    def __iter__(self) -> Iterator[int]:
        yield self.y
        yield self.x

    def __add__(self, other: Self) -> Self:
        return type(self)(self.y + other.y, self.x + other.x)

    def __sub__(self, other: Self) -> Self:
        return type(self)(self.y - other.y, self.x - other.x)

    def __mul__(self, scalar: int) -> Self:
        return type(self)(self.y * scalar, self.x * scalar)

    def __floordiv__(self, scalar: int) -> Self:
        return type(self)(self.y // scalar, self.x // scalar)

    def __neg__(self) -> Self:
        return type(self)(-self.y, -self.x)

    def to_str(self) -> str:
        """Serialize to 'y,x' string."""
        return f"{self.y},{self.x}"

    @classmethod
    def from_str(cls, s: str) -> Self:
        """Parse from 'y,x' string."""
        parts = s.split(",")
        if len(parts) != 2:
            raise ValueError(f"Expected 'y,x' format, got '{s}'")
        return cls(int(parts[0]), int(parts[1]))

    @classmethod
    def parse(cls, v: "list[int] | tuple[int, int] | dict[str, int] | str") -> Self:
        """Parse from various formats: [y, x], (y, x), {'y': ..., 'x': ...}, or 'y,x' string."""
        if isinstance(v, str):
            return cls.from_str(v)
        if isinstance(v, dict):
            return cls(y=int(v["y"]), x=int(v["x"]))
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return cls(y=int(v[0]), x=int(v[1]))
        raise ValueError(f"Cannot parse {type(v).__name__} as {cls.__name__}")

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return {"y": self.y, "x": self.x}

    def to_float(self) -> Vec2D:
        """Convert to float vector."""
        return Vec2D(float(self.y), float(self.x))

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.union_schema(
            [
                core_schema.is_instance_schema(cls),
                core_schema.no_info_plain_validator_function(cls.parse),
            ],
            serialization=core_schema.plain_serializer_function_ser_schema(lambda v: v.to_str()),
        )


# === 3D Vectors ===


@dataclass(frozen=True, slots=True)
class Vec3D:
    """Float 3D vector with z,y,x components.

    Use for physical positions, volumes, voxel sizes, etc.

    Examples:
        stage_pos = Vec3D(z=100.0, y=1000.5, x=500.0)  # micrometers
        voxel_size = Vec3D(z=2.0, y=0.5, x=0.5)        # micrometers
    """

    z: float
    y: float
    x: float

    def __iter__(self) -> Iterator[float]:
        yield self.z
        yield self.y
        yield self.x

    def __add__(self, other: Self) -> Self:
        return type(self)(self.z + other.z, self.y + other.y, self.x + other.x)

    def __sub__(self, other: Self) -> Self:
        return type(self)(self.z - other.z, self.y - other.y, self.x - other.x)

    def __mul__(self, scalar: float) -> Self:
        return type(self)(self.z * scalar, self.y * scalar, self.x * scalar)

    def __truediv__(self, scalar: float) -> Self:
        return type(self)(self.z / scalar, self.y / scalar, self.x / scalar)

    def __floordiv__(self, scalar: float) -> Self:
        return type(self)(self.z // scalar, self.y // scalar, self.x // scalar)

    def __neg__(self) -> Self:
        return type(self)(-self.z, -self.y, -self.x)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(z={self.z}, y={self.y}, x={self.x})"

    def to_str(self) -> str:
        """Serialize to 'z,y,x' string."""
        return f"{self.z},{self.y},{self.x}"

    @classmethod
    def from_str(cls, s: str) -> Self:
        """Parse from 'z,y,x' string."""
        parts = s.split(",")
        if len(parts) != 3:
            raise ValueError(f"Expected 'z,y,x' format, got '{s}'")
        return cls(float(parts[0]), float(parts[1]), float(parts[2]))

    @classmethod
    def parse(cls, v: "list[float] | tuple[float, float, float] | dict[str, float] | str") -> Self:
        """Parse from various formats: [z, y, x], (z, y, x), {'z': ..., 'y': ..., 'x': ...}, or 'z,y,x' string."""
        if isinstance(v, str):
            return cls.from_str(v)
        if isinstance(v, dict):
            return cls(z=float(v["z"]), y=float(v["y"]), x=float(v["x"]))
        if isinstance(v, (list, tuple)) and len(v) == 3:
            return cls(z=float(v[0]), y=float(v[1]), x=float(v[2]))
        raise ValueError(f"Cannot parse {type(v).__name__} as {cls.__name__}")

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {"z": self.z, "y": self.y, "x": self.x}

    def to_int(self) -> "IVec3D":
        """Convert to integer vector (truncates toward zero)."""
        return IVec3D(int(self.z), int(self.y), int(self.x))

    @property
    def xy(self) -> Vec2D:
        """Get the y,x components as a Vec2D."""
        return Vec2D(self.y, self.x)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.union_schema(
            [
                core_schema.is_instance_schema(cls),
                core_schema.no_info_plain_validator_function(cls.parse),
            ],
            serialization=core_schema.plain_serializer_function_ser_schema(lambda v: v.to_str()),
        )


@dataclass(frozen=True, slots=True)
class IVec3D:
    """Integer 3D vector with z,y,x components.

    Use for voxel coordinates, stack dimensions, array shapes, etc.

    Examples:
        stack_shape = IVec3D(z=100, y=2048, x=2048)  # voxels
        voxel_pos = IVec3D(z=50, y=1024, x=512)      # indices
    """

    z: int
    y: int
    x: int

    def __iter__(self) -> Iterator[int]:
        yield self.z
        yield self.y
        yield self.x

    def __add__(self, other: Self) -> Self:
        return type(self)(self.z + other.z, self.y + other.y, self.x + other.x)

    def __sub__(self, other: Self) -> Self:
        return type(self)(self.z - other.z, self.y - other.y, self.x - other.x)

    def __mul__(self, scalar: int) -> Self:
        return type(self)(self.z * scalar, self.y * scalar, self.x * scalar)

    def __floordiv__(self, scalar: int) -> Self:
        return type(self)(self.z // scalar, self.y // scalar, self.x // scalar)

    def __neg__(self) -> Self:
        return type(self)(-self.z, -self.y, -self.x)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(z={self.z}, y={self.y}, x={self.x})"

    def to_str(self) -> str:
        """Serialize to 'z,y,x' string."""
        return f"{self.z},{self.y},{self.x}"

    @classmethod
    def from_str(cls, s: str) -> Self:
        """Parse from 'z,y,x' string."""
        parts = s.split(",")
        if len(parts) != 3:
            raise ValueError(f"Expected 'z,y,x' format, got '{s}'")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    @classmethod
    def parse(cls, v: "list[int] | tuple[int, int, int] | dict[str, int] | str") -> Self:
        """Parse from various formats: [z, y, x], (z, y, x), {'z': ..., 'y': ..., 'x': ...}, or 'z,y,x' string."""
        if isinstance(v, str):
            return cls.from_str(v)
        if isinstance(v, dict):
            return cls(z=int(v["z"]), y=int(v["y"]), x=int(v["x"]))
        if isinstance(v, (list, tuple)) and len(v) == 3:
            return cls(z=int(v[0]), y=int(v[1]), x=int(v[2]))
        raise ValueError(f"Cannot parse {type(v).__name__} as {cls.__name__}")

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return {"z": self.z, "y": self.y, "x": self.x}

    def to_float(self) -> Vec3D:
        """Convert to float vector."""
        return Vec3D(float(self.z), float(self.y), float(self.x))

    @property
    def xy(self) -> IVec2D:
        """Get the y,x components as an IVec2D."""
        return IVec2D(self.y, self.x)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.union_schema(
            [
                core_schema.is_instance_schema(cls),
                core_schema.no_info_plain_validator_function(cls.parse),
            ],
            serialization=core_schema.plain_serializer_function_ser_schema(lambda v: v.to_str()),
        )


# === Positive-validated variants ===


def _check_positive_2d(name: str, y: float, x: float) -> None:
    if y <= 0 or x <= 0:
        raise ValueError(f"{name}: all components must be positive, got y={y}, x={x}")


def _check_positive_3d(name: str, z: float, y: float, x: float) -> None:
    if z <= 0 or y <= 0 or x <= 0:
        raise ValueError(f"{name}: all components must be positive, got z={z}, y={y}, x={x}")


@final
@dataclass(frozen=True, slots=True)
class UVec2D(Vec2D):
    """Positive float 2D vector. All components must be > 0."""

    def __post_init__(self):
        _check_positive_2d(type(self).__name__, self.y, self.x)


@final
@dataclass(frozen=True, slots=True)
class UIVec2D(IVec2D):
    """Positive integer 2D vector. All components must be > 0."""

    def __post_init__(self):
        _check_positive_2d(type(self).__name__, self.y, self.x)


@final
@dataclass(frozen=True, slots=True)
class UVec3D(Vec3D):
    """Positive float 3D vector. All components must be > 0."""

    def __post_init__(self):
        _check_positive_3d(type(self).__name__, self.z, self.y, self.x)


@final
@dataclass(frozen=True, slots=True)
class UIVec3D(IVec3D):
    """Positive integer 3D vector. All components must be > 0."""

    def __post_init__(self):
        _check_positive_3d(type(self).__name__, self.z, self.y, self.x)
