"""Vector types for 2D and 3D coordinates.

Provides float, integer, and non-negative-validated variants:
- Vec2D, Vec3D: Float vectors for physical coordinates (micrometers, etc.)
- IVec2D, IVec3D: Integer vectors for pixel coordinates, shapes, etc.
- UVec2D, UVec3D: Non-negative float vectors (all components >= 0)
- UIVec2D, UIVec3D: Non-negative (unsigned) integer vectors (all components >= 0)
- Span: 2 numbers in the order they were given, with ``low`` and ``high``

Components are named everywhere: vectors are built with keywords, and they are saved as maps such as
``{x: 1.5, y: 2.0}``. Iterating yields y,x (and z,y,x), the order of NumPy array indexes.
"""

import math
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, NamedTuple, Self, final

from pydantic import Field, GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _whole(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)) or (isinstance(value, float) and value.is_integer())


def _schema(parse: Callable[[Any], Any]) -> CoreSchema:
    return core_schema.no_info_plain_validator_function(
        parse, serialization=core_schema.plain_serializer_function_ser_schema(lambda v: v.to_dict())
    )


# === 2D Vectors ===


@dataclass(frozen=True, slots=True, kw_only=True)
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
        return type(self)(y=self.y + other.y, x=self.x + other.x)

    def __sub__(self, other: Self) -> Self:
        return type(self)(y=self.y - other.y, x=self.x - other.x)

    def __mul__(self, scalar: float) -> Self:
        return type(self)(y=self.y * scalar, x=self.x * scalar)

    def __truediv__(self, scalar: float) -> Self:
        return type(self)(y=self.y / scalar, x=self.x / scalar)

    def __floordiv__(self, scalar: float) -> Self:
        return type(self)(y=self.y // scalar, x=self.x // scalar)

    def __neg__(self) -> Self:
        return type(self)(y=-self.y, x=-self.x)

    @classmethod
    def parse(cls, v: object) -> Self:
        """Parse from a map of finite numbers with exactly the keys x, y."""
        if isinstance(v, cls):
            return v
        if isinstance(v, Mapping) and set(v) == {"y", "x"} and all(map(_finite, v.values())):
            return cls(y=float(v["y"]), x=float(v["x"]))
        raise ValueError(f"Expected a map with keys x, y for {cls.__name__}, got {v!r}")

    def to_dict(self) -> dict[str, float]:
        """The saved form: a map from component name to value."""
        return {"x": self.x, "y": self.y}

    def to_int(self) -> "IVec2D":
        """Convert to integer vector (truncates toward zero)."""
        return IVec2D(y=int(self.y), x=int(self.x))

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return _schema(cls.parse)


@dataclass(frozen=True, slots=True, kw_only=True)
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
        return type(self)(y=self.y + other.y, x=self.x + other.x)

    def __sub__(self, other: Self) -> Self:
        return type(self)(y=self.y - other.y, x=self.x - other.x)

    def __mul__(self, scalar: int) -> Self:
        return type(self)(y=self.y * scalar, x=self.x * scalar)

    def __floordiv__(self, scalar: int) -> Self:
        return type(self)(y=self.y // scalar, x=self.x // scalar)

    def __neg__(self) -> Self:
        return type(self)(y=-self.y, x=-self.x)

    @classmethod
    def parse(cls, v: object) -> Self:
        """Parse from a map of whole numbers with exactly the keys x, y."""
        if isinstance(v, cls):
            return v
        if isinstance(v, Mapping) and set(v) == {"y", "x"} and all(map(_whole, v.values())):
            return cls(y=int(v["y"]), x=int(v["x"]))
        raise ValueError(f"Expected a map with keys x, y for {cls.__name__}, got {v!r}")

    def to_dict(self) -> dict[str, int]:
        """The saved form: a map from component name to value."""
        return {"x": self.x, "y": self.y}

    def to_float(self) -> Vec2D:
        """Convert to float vector."""
        return Vec2D(y=float(self.y), x=float(self.x))

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return _schema(cls.parse)


# === 3D Vectors ===


@dataclass(frozen=True, slots=True, kw_only=True)
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
        return type(self)(z=self.z + other.z, y=self.y + other.y, x=self.x + other.x)

    def __sub__(self, other: Self) -> Self:
        return type(self)(z=self.z - other.z, y=self.y - other.y, x=self.x - other.x)

    def __mul__(self, scalar: float) -> Self:
        return type(self)(z=self.z * scalar, y=self.y * scalar, x=self.x * scalar)

    def __truediv__(self, scalar: float) -> Self:
        return type(self)(z=self.z / scalar, y=self.y / scalar, x=self.x / scalar)

    def __floordiv__(self, scalar: float) -> Self:
        return type(self)(z=self.z // scalar, y=self.y // scalar, x=self.x // scalar)

    def __neg__(self) -> Self:
        return type(self)(z=-self.z, y=-self.y, x=-self.x)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(z={self.z}, y={self.y}, x={self.x})"

    @classmethod
    def parse(cls, v: object) -> Self:
        """Parse from a map of finite numbers with exactly the keys x, y, z."""
        if isinstance(v, cls):
            return v
        if isinstance(v, Mapping) and set(v) == {"z", "y", "x"} and all(map(_finite, v.values())):
            return cls(z=float(v["z"]), y=float(v["y"]), x=float(v["x"]))
        raise ValueError(f"Expected a map with keys x, y, z for {cls.__name__}, got {v!r}")

    def to_dict(self) -> dict[str, float]:
        """The saved form: a map from component name to value."""
        return {"x": self.x, "y": self.y, "z": self.z}

    def to_int(self) -> "IVec3D":
        """Convert to integer vector (truncates toward zero)."""
        return IVec3D(z=int(self.z), y=int(self.y), x=int(self.x))

    @property
    def xy(self) -> Vec2D:
        """Get the y,x components as a Vec2D."""
        return Vec2D(y=self.y, x=self.x)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return _schema(cls.parse)


@dataclass(frozen=True, slots=True, kw_only=True)
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
        return type(self)(z=self.z + other.z, y=self.y + other.y, x=self.x + other.x)

    def __sub__(self, other: Self) -> Self:
        return type(self)(z=self.z - other.z, y=self.y - other.y, x=self.x - other.x)

    def __mul__(self, scalar: int) -> Self:
        return type(self)(z=self.z * scalar, y=self.y * scalar, x=self.x * scalar)

    def __floordiv__(self, scalar: int) -> Self:
        return type(self)(z=self.z // scalar, y=self.y // scalar, x=self.x // scalar)

    def __neg__(self) -> Self:
        return type(self)(z=-self.z, y=-self.y, x=-self.x)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(z={self.z}, y={self.y}, x={self.x})"

    @classmethod
    def parse(cls, v: object) -> Self:
        """Parse from a map of whole numbers with exactly the keys x, y, z."""
        if isinstance(v, cls):
            return v
        if isinstance(v, Mapping) and set(v) == {"z", "y", "x"} and all(map(_whole, v.values())):
            return cls(z=int(v["z"]), y=int(v["y"]), x=int(v["x"]))
        raise ValueError(f"Expected a map with keys x, y, z for {cls.__name__}, got {v!r}")

    def to_dict(self) -> dict[str, int]:
        """The saved form: a map from component name to value."""
        return {"x": self.x, "y": self.y, "z": self.z}

    def to_float(self) -> Vec3D:
        """Convert to float vector."""
        return Vec3D(z=float(self.z), y=float(self.y), x=float(self.x))

    @property
    def xy(self) -> IVec2D:
        """Get the y,x components as an IVec2D."""
        return IVec2D(y=self.y, x=self.x)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return _schema(cls.parse)


# === Positive-validated variants ===


def _check_non_negative_2d(name: str, y: float, x: float) -> None:
    if y < 0 or x < 0:
        raise ValueError(f"{name}: all components must be non-negative, got y={y}, x={x}")


def _check_non_negative_3d(name: str, z: float, y: float, x: float) -> None:
    if z < 0 or y < 0 or x < 0:
        raise ValueError(f"{name}: all components must be non-negative, got z={z}, y={y}, x={x}")


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class UVec2D(Vec2D):
    """Non-negative float 2D vector. All components must be >= 0."""

    def __post_init__(self):
        _check_non_negative_2d(type(self).__name__, self.y, self.x)


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class UIVec2D(IVec2D):
    """Non-negative (unsigned) integer 2D vector. All components must be >= 0."""

    def __post_init__(self):
        _check_non_negative_2d(type(self).__name__, self.y, self.x)


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class UVec3D(Vec3D):
    """Non-negative float 3D vector. All components must be >= 0."""

    def __post_init__(self):
        _check_non_negative_3d(type(self).__name__, self.z, self.y, self.x)


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class UIVec3D(IVec3D):
    """Non-negative (unsigned) integer 3D vector. All components must be >= 0."""

    def __post_init__(self):
        _check_non_negative_3d(type(self).__name__, self.z, self.y, self.x)


# === Span ===


class Span(NamedTuple):
    """2 numbers in the order they were given, saved as a pair such as ``[0, 5]``. ``low`` and ``high`` ignore it."""

    a: Annotated[float, Field(allow_inf_nan=False)]
    b: Annotated[float, Field(allow_inf_nan=False)]

    @property
    def low(self) -> float:
        return min(self.a, self.b)

    @property
    def high(self) -> float:
        return max(self.a, self.b)

    @property
    def length(self) -> float:
        return self.high - self.low

    @property
    def middle(self) -> float:
        return (self.a + self.b) / 2
