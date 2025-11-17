import math
import re
from collections.abc import Callable, Generator
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

_TIME_UNITS = {
    "s": 1.0,
    "seconds": 1.0,
    "second": 1.0,
    "ms": 1e-3,
    "us": 1e-6,
    "ns": 1e-9,
}
_FREQUENCY_UNITS = {
    "hz": 1.0,
    "khz": 1e3,
    "mhz": 1e6,
}
_VOLTAGE_UNITS = {
    "v": 1.0,
    "mv": 1e-3,
    "uv": 1e-6,
}
_ANGLE_UNITS = {
    "deg": math.pi / 180.0,  # degrees to radians
    "°": math.pi / 180.0,  # degrees to radians
}

_UNIT_FACTORS = {
    **_TIME_UNITS,
    **_FREQUENCY_UNITS,
    **_VOLTAGE_UNITS,
    **_ANGLE_UNITS,
}


class QuantityValidationError(ValueError):
    """Custom exception for quantity validation errors."""

    def __init__(self, value: float | str, reason: str = "Invalid quantity") -> None:
        self.value = value
        self.message = reason
        super().__init__(f"{reason}: {value!r}")


class Quantity(float):
    UNIT_FACTORS = _UNIT_FACTORS

    def __new__(cls, v: float | str) -> Self:
        # Direct instantiation also parses unit strings
        parsed = cls._validate(v)
        return super().__new__(cls, parsed)

    @classmethod
    def __get_validators__(cls) -> Generator[Callable[..., float], Any, None]:
        yield cls._validate

    @classmethod
    def _validate(cls, v: float | str, *args, **kwargs) -> float:  # noqa: ARG003, ANN002, ANN003
        if isinstance(v, (int, float)):
            return float(v)
        m = re.fullmatch(r"\s*([+-]?[0-9]*\.?[0-9]+)\s*([a-zA-Z°]+)\s*", str(v))
        if not m:
            raise QuantityValidationError(v, "Couldn't parse quantity")
        val, unit = float(m[1]), m[2].lower()
        if unit in ("deg", "°"):
            return math.radians(val)
        factor = cls.UNIT_FACTORS.get(unit)
        if factor is None:
            raise QuantityValidationError(v, "Unknown unit")
        return val * factor


class Time(Quantity):
    UNIT_FACTORS = _TIME_UNITS


class Frequency(Quantity):
    UNIT_FACTORS = _FREQUENCY_UNITS


class Voltage(Quantity):
    UNIT_FACTORS = _VOLTAGE_UNITS


class Angle(Quantity):
    UNIT_FACTORS = _ANGLE_UNITS


class _QuantityRange[Q: Quantity](BaseModel):
    min: Q | float = Field(..., description="Minimum value of the range")
    max: Q | float = Field(..., description="Maximum value of the range")

    @model_validator(mode="after")
    def check_range(self) -> Self:
        if self.max <= self.min:
            err = f"Range end must be greater than start (got min={self.min}, max={self.max})"
            raise ValueError(err)
        return self

    @property
    def span(self) -> float:
        return float(self.max - self.min)


class QuantityRange[Q: Quantity](BaseModel):
    min: Q | float = Field(default=float("nan"), description="Minimum value of the range")
    max: Q | float = Field(default=float("nan"), description="Maximum value of the range")
    span: Q | float = Field(default=float("nan"), description="Span of the range")

    @model_validator(mode="after")
    def check_inputs(self) -> Self:
        if math.isnan(self.max) and not math.isnan(self.min) and not math.isnan(self.span):
            self.max = self.min + self.span
        elif math.isnan(self.min) and not math.isnan(self.max) and not math.isnan(self.span):
            self.min = self.max - self.span
        elif math.isnan(self.span) and not math.isnan(self.min) and not math.isnan(self.max):
            if self.max <= self.min:
                err = "Range end must be greater than start"
                raise ValueError(err)
            self.span = self.max - self.min
        elif math.isnan(self.min) and math.isnan(self.max) and not math.isnan(self.span):
            err = "At least 'min' or 'max' must be provided if 'span' is given."
            raise ValueError(err)
        elif math.isnan(self.min) and math.isnan(self.max) and math.isnan(self.span):
            err = "At least two of 'min', 'max', or 'span' must be provided."
            raise ValueError(err)
        return self


class NormalizedRange(BaseModel):
    min: float = Field(default=float("nan"), ge=0.0)
    max: float = Field(default=float("nan"), le=1.0)
    span: float = Field(default=float("nan"), ge=0.0)

    @model_validator(mode="after")
    def check_range(self) -> Self:
        if math.isnan(self.max) and not math.isnan(self.min) and not math.isnan(self.span):
            self.max = self.min + self.span
        elif math.isnan(self.min) and not math.isnan(self.max) and not math.isnan(self.span):
            self.min = self.max - self.span
        elif math.isnan(self.span) and not math.isnan(self.min) and not math.isnan(self.max):
            if self.max <= self.min:
                err = "Range end must be greater than start"
                raise ValueError(err)
            self.span = self.max - self.min
        elif math.isnan(self.min) and math.isnan(self.max) and not math.isnan(self.span):
            err = "At least 'min' or 'max' must be provided if 'span' is given."
            raise ValueError(err)
        elif math.isnan(self.min) and math.isnan(self.max) and math.isnan(self.span):
            self.min = 0.0
            self.max = 1.0
            self.span = 1.0
        return self


VoltageRange = QuantityRange[Voltage]
FrequencyRange = QuantityRange[Frequency]
AngleRange = QuantityRange[Angle]
TimeWindow = QuantityRange[Time]
