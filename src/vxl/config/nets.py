"""Nets: the lines on the bench, each with 1 sending pin, its receiving pins and its kind."""

from collections.abc import Mapping
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Discriminator, Field, Tag, field_validator, model_validator
from vxlib.schema import FrozenModel, check_identifier, identifier, repeated
from vxlib.units import Quantity, Time, Voltage

Connector = Annotated[str, identifier("Connector")]
"""A connector that a device class declares, named as it is on the hardware."""
UnitName = Annotated[str, Field(min_length=1)]
"""The name of a unit, such as ``V``, ``mm`` or ``deg``."""
type NetKind = Literal["digital", "analog"]


def split_pin(ref: str) -> tuple[str, str]:
    """Split a pin written ``device/connector`` into its device and connector."""
    device, _, connector = ref.partition("/")
    return device, connector


def _check_pin(ref: str) -> str:
    device, sep, connector = ref.partition("/")
    if not sep or "/" in connector:
        raise ValueError(f"a pin is written 'device/connector', got {ref!r}")
    check_identifier(device, "Device UID")
    check_identifier(connector, "Connector")
    return ref


Pin = Annotated[str, AfterValidator(_check_pin)]
"""A connector of a device, written ``camera/trigger_in``."""


class DigitalKind(FrozenModel):
    """A line with 2 levels.

    ``off`` and ``on`` are given when the sending pin is analog, and left out when the hardware fixes the levels.
    The times are the shortest pulse, gap and period that the receiving device accepts.
    """

    off: Voltage | None = None
    on: Voltage | None = None
    on_time: Time | None = None
    off_time: Time | None = None
    repeat_time: Time | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.off is None) != (self.on is None):
            raise ValueError("give both 'off' and 'on', or neither")
        if self.off is not None and self.off == self.on:
            raise ValueError("'off' and 'on' must differ")
        for name in ("on_time", "off_time", "repeat_time"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"'{name}' must be greater than 0")
        return self


class AnalogKind(FrozenModel):
    """A line whose value moves continuously, in its own ``unit``.

    ``scales`` turn the unit into volts through 1 or more tables, each with 2 columns: its own unit and the unit
    below it, for example ``{mm: {mm: [...], deg: [...]}, deg: {deg: [...], V: [...]}}``. ``limits`` may be given
    in any unit on that path, with the unit as the key. ``park`` is written in the net's unit, such as ``0 V``.
    """

    unit: UnitName = "V"
    scales: dict[UnitName, dict[UnitName, list[float]]] = Field(default_factory=dict)
    limits: dict[UnitName, tuple[float, float]] = Field(default_factory=dict)
    park: Quantity | None = None
    travel_time: Time | None = None
    jerk_time: Time | None = None

    @property
    def units(self) -> list[UnitName]:
        """The units a value passes through, from the net's unit down to V."""
        path = [self.unit]
        while path[-1] != "V" and path[-1] in self.scales:
            below = next(key for key in self.scales[path[-1]] if key != path[-1])
            if below in path:
                break
            path.append(below)
        return path

    @model_validator(mode="after")
    def _check(self) -> Self:
        for unit, table in self.scales.items():
            _check_scale(unit, table)
        path = self.units
        if path[-1] != "V":
            raise ValueError(f"scales must lead from '{self.unit}' down to 'V' (they stop at '{path[-1]}')")
        if unused := sorted(set(self.scales) - set(path)):
            raise ValueError(f"scales for {unused} are not on the path from '{self.unit}' to 'V'")
        for unit, (low, high) in self.limits.items():
            if unit not in path:
                raise ValueError(f"limits in '{unit}' are not on the path {path}")
            if not low < high:
                raise ValueError(f"limits in '{unit}' must rise, got [{low}, {high}]")
        if self.park is not None:
            self._check_park(self.park)
        if self.travel_time is not None and self.travel_time <= 0:
            raise ValueError("'travel_time' must be greater than 0")
        if self.jerk_time is not None:
            if self.travel_time is None:
                raise ValueError("'jerk_time' needs 'travel_time'")
            if self.jerk_time <= 0:
                raise ValueError("'jerk_time' must be greater than 0")
        return self

    def _check_park(self, park: Quantity) -> None:
        if park.unit != self.unit:
            raise ValueError(f"park is in {park.unit}; this net's unit is {self.unit}")
        if self.unit in self.limits:
            low, high = self.limits[self.unit]
            if not low <= park <= high:
                raise ValueError(f"park {park} is outside the limits [{low}, {high}] {self.unit}")


def _check_scale(unit: str, table: Mapping[str, list[float]]) -> None:
    if unit == "V":
        raise ValueError("'V' needs no scale")
    if unit not in table or len(table) != 2:
        raise ValueError(f"the scale for '{unit}' needs 2 columns: '{unit}' and the unit below it")
    columns = list(table.values())
    if len(columns[0]) != len(columns[1]) or len(columns[0]) < 2:
        raise ValueError(f"the columns of the scale for '{unit}' need the same length, at least 2")
    for name, column in table.items():
        steps = [b - a for a, b in pairwise(column)]
        if not (all(step > 0 for step in steps) or all(step < 0 for step in steps)):
            raise ValueError(f"column '{name}' of the scale for '{unit}' must rise or fall at every row")


class _NetBase(FrozenModel):
    pin: Connector
    """The sending device's connector."""
    to: list[Pin]
    """The receiving pins, or ``[]`` when the line reaches no device in ``hal``, such as a galvo."""

    @field_validator("to")
    @classmethod
    def _unique_pins(cls, value: list[str]) -> list[str]:
        if duplicates := repeated(value):
            raise ValueError(f"pins in 'to' must be unique (repeated: {duplicates})")
        return value


class DigitalNet(_NetBase):
    """A line with 2 levels."""

    digital: DigitalKind

    @property
    def kind(self) -> NetKind:
        return "digital"


class AnalogNet(_NetBase):
    """A line whose value moves continuously."""

    analog: AnalogKind

    @property
    def kind(self) -> NetKind:
        return "analog"


def _net_kind(value: object) -> str | None:
    if isinstance(value, Mapping):
        kinds = [kind for kind in ("digital", "analog") if kind in value]
        return kinds[0] if len(kinds) == 1 else None
    return value.kind if isinstance(value, DigitalNet | AnalogNet) else None


type Net = Annotated[
    Annotated[DigitalNet, Tag("digital")] | Annotated[AnalogNet, Tag("analog")],
    Discriminator(
        _net_kind, custom_error_type="one_key", custom_error_message="write exactly 1 of: 'digital', 'analog'"
    ),
]
"""1 line: the sending device's connector, the pins it reaches, and its kind as 1 key, ``digital`` or ``analog``."""


__all__ = [
    "AnalogKind",
    "AnalogNet",
    "Connector",
    "DigitalKind",
    "DigitalNet",
    "Net",
    "NetKind",
    "Pin",
    "UnitName",
    "split_pin",
]
