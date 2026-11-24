"""Numbers that keep the unit they were written in, such as ``25 ms`` or ``3.13 V``.

A value is read only from text with its unit and is saved back as it was written. As a float it is the value in
its kind's base unit, so ``Time("25 ms")`` computes as 0.025 s. Arithmetic gives a plain float.
"""

import math
import re
from typing import Annotated, Any, ClassVar, Self

from pydantic import AfterValidator, GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema

_NUMBER = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_UNIT = r"[^\s\d.+-]\S*"
"""A unit: text with no space, which does not start as a number does."""
_NO_UNIT = rf"(?!\s*{_NUMBER}\s*$)"
"""Text that is only a number has no unit: ``12`` and ``3e2`` are no values, though their ends could pass as units."""
_TEXT = re.compile(rf"{_NO_UNIT}\s*({_NUMBER})\s*({_UNIT})\s*")


class Quantity(float):
    """A number in a named unit. A plain ``Quantity`` takes any unit and keeps the number as written."""

    UNITS: ClassVar[dict[str, float] | None] = None
    """Each unit with its factor to the base unit, or ``None`` to take any unit with no conversion."""

    number: float
    unit: str
    written: str

    def __new__(cls, text: str) -> Self:
        match = _TEXT.fullmatch(text) if isinstance(text, str) else None
        if match is None:
            example = f"25 {next(iter(cls.UNITS))}" if cls.UNITS else "3.13 V"
            raise ValueError(f"write a number and a unit, such as '{example}', got {text!r}")
        self = cls.of(float(match[1]), match[2])
        self.written = match[1]
        return self

    @classmethod
    def of(cls, number: float, unit: str) -> Self:
        """Build a value from a number and a unit, for code that has a number rather than text."""
        if not math.isfinite(number):
            raise ValueError(f"{cls.__name__} must be finite, got {number}")
        if cls.UNITS is None:
            factor = 1.0
        elif (found := cls.UNITS.get(unit)) is None:
            raise ValueError(f"'{unit}' is not a {cls.__name__} unit (use {', '.join(cls.UNITS)})")
        else:
            factor = found
        self = super().__new__(cls, number * factor)
        self.number, self.unit, self.written = number, unit, repr(number)
        return self

    def __str__(self) -> str:
        return f"{self.written} {self.unit}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self)!r})"

    def __reduce__(self) -> tuple[type[Self], tuple[str]]:
        return type(self), (str(self),)

    @classmethod
    def __get_pydantic_core_schema__(cls, _source: Any, _handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            lambda value: value if isinstance(value, cls) else cls(value),
            serialization=core_schema.plain_serializer_function_ser_schema(str, return_schema=core_schema.str_schema()),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, _schema: CoreSchema, _handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        units = "|".join(re.escape(unit) for unit in cls.UNITS) if cls.UNITS else _UNIT
        return {"type": "string", "pattern": rf"^{_NO_UNIT}\s*{_NUMBER}\s*({units})\s*$"}


class Time(Quantity):
    """Base unit: seconds."""

    UNITS: ClassVar[dict[str, float] | None] = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9}


class Frequency(Quantity):
    """Base unit: hertz."""

    UNITS: ClassVar[dict[str, float] | None] = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6}


class Voltage(Quantity):
    """Base unit: volts."""

    UNITS: ClassVar[dict[str, float] | None] = {"V": 1.0, "mV": 1e-3, "uV": 1e-6}


class Angle(Quantity):
    """Base unit: radians."""

    UNITS: ClassVar[dict[str, float] | None] = {"rad": 1.0, "deg": math.pi / 180, "°": math.pi / 180}


class Wavelength(Quantity):
    """Base unit: nanometers."""

    UNITS: ClassVar[dict[str, float] | None] = {"nm": 1.0, "um": 1e3}


class Percent(Quantity):
    """A part of a whole. Base unit: the fraction, so ``5 %`` is 0.05."""

    UNITS: ClassVar[dict[str, float] | None] = {"%": 0.01}


def _below_whole(value: Percent) -> Percent:
    if not 0 <= value < 1:
        raise ValueError(f"must be at least 0 % and below 100 %, got {value}")
    return value


Portion = Annotated[Percent, AfterValidator(_below_whole)]
"""A part of a whole from 0 % up to, but not including, 100 %, such as an overlap or a margin."""


__all__ = ["Angle", "Frequency", "Percent", "Portion", "Quantity", "Time", "Voltage", "Wavelength"]
