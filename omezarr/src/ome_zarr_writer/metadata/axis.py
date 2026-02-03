from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, Field
from vxlib import SchemaModel


class AxisName(StrEnum):
    """OME-Zarr axis names."""

    X = "x"
    Y = "y"
    Z = "z"
    C = "c"
    T = "t"


class AxisType(StrEnum):
    """OME-Zarr axis types."""

    SPACE = "space"
    TIME = "time"
    CHANNEL = "channel"


class SpaceUnit(StrEnum):
    """Spatial units for OME-Zarr axes."""

    METER = "meter"
    MICROMETER = "micrometer"
    NANOMETER = "nanometer"
    MILLIMETER = "millimeter"
    INCH = "inch"
    FOOT = "foot"


class TimeUnit(StrEnum):
    """Time units for OME-Zarr axes."""

    SECOND = "second"
    MILLISECOND = "millisecond"
    MICROSECOND = "microsecond"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"


class SpaceAxis(SchemaModel):
    """Represents a spatial axis (x, y, or z)."""

    name: Literal[AxisName.X, AxisName.Y, AxisName.Z]
    type: Literal[AxisType.SPACE] = AxisType.SPACE
    unit: SpaceUnit

    @classmethod
    def axes(cls, unit: SpaceUnit) -> list["SpaceAxis"]:
        return [
            cls(name=AxisName.Z, unit=unit),
            cls(name=AxisName.Y, unit=unit),
            cls(name=AxisName.X, unit=unit),
        ]


class TimeAxis(SchemaModel):
    """Represents a time axis."""

    name: Literal[AxisName.T] = AxisName.T
    type: Literal[AxisType.TIME] = AxisType.TIME
    unit: TimeUnit


class ChannelAxis(SchemaModel):
    """Represents a channel axis."""

    name: Literal[AxisName.C] = AxisName.C
    type: Literal[AxisType.CHANNEL] = AxisType.CHANNEL


# Discriminated union of all axis types
Axis = Annotated[
    SpaceAxis | TimeAxis | ChannelAxis,
    Field(discriminator="type"),
]


def validate_multiscale_axes(value: list) -> list[Axis]:
    """Validate axes requirements for OME-Zarr multiscales.

    Per OME-Zarr spec:
    - 2-5 dimensions total
    - Must have 2-3 space axes
    - May have at most 1 time axis
    - May have at most 1 channel axis
    - Order: time (if present), channel (if present), space axes
    """
    if not isinstance(value, list):
        raise ValueError(f"axes must be a list, got {type(value)}")

    # Check length
    if not (2 <= len(value) <= 5):
        raise ValueError(f"Must have 2-5 axes, found {len(value)}")

    # Count axes by type
    space_axes = [ax for ax in value if isinstance(ax, SpaceAxis)]
    time_axes = [ax for ax in value if isinstance(ax, TimeAxis)]
    channel_axes = [ax for ax in value if isinstance(ax, ChannelAxis)]

    # Must have 2-3 space axes
    if not (2 <= len(space_axes) <= 3):
        raise ValueError(f"Must have 2-3 space axes, found {len(space_axes)}")

    # May have at most 1 time axis
    if len(time_axes) > 1:
        raise ValueError(f"May have at most 1 time axis, found {len(time_axes)}")

    # May have at most 1 channel axis
    if len(channel_axes) > 1:
        raise ValueError(f"May have at most 1 channel axis, found {len(channel_axes)}")

    # Validate ordering: time, then channel, then space
    time_idx = [i for i, ax in enumerate(value) if isinstance(ax, TimeAxis)]
    channel_idx = [i for i, ax in enumerate(value) if isinstance(ax, ChannelAxis)]
    space_idx = [i for i, ax in enumerate(value) if isinstance(ax, SpaceAxis)]

    if time_idx and channel_idx and time_idx[0] > channel_idx[0]:
        raise ValueError("Time axis must come before channel axis")

    if time_idx and space_idx and time_idx[0] > space_idx[0]:
        raise ValueError("Time axis must come before space axes")

    if channel_idx and space_idx and channel_idx[0] > space_idx[0]:
        raise ValueError("Channel axis must come before space axes")

    return value


# Type alias for multiscale axes with validation
MultiscaleAxes = Annotated[
    list[Axis],
    AfterValidator(validate_multiscale_axes),
    Field(min_length=2, max_length=5),
]


__all__ = [
    "AxisName",
    "AxisType",
    "SpaceUnit",
    "TimeUnit",
    "Axis",
    "SpaceAxis",
    "TimeAxis",
    "ChannelAxis",
    "MultiscaleAxes",
]
