import math
import re

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


class Quantity(float):
    UNIT_FACTORS = _UNIT_FACTORS

    def __new__(cls, v: float | str | int):
        # Direct instantiation also parses unit strings
        parsed = cls._validate(v)
        return super().__new__(cls, parsed)

    @classmethod
    def __get_validators__(cls):
        yield cls._validate

    @classmethod
    def _validate(cls, v, *args, **kwargs):
        if isinstance(v, (int, float)):
            return float(v)
        m = re.fullmatch(r"\s*([+-]?[0-9]*\.?[0-9]+)\s*([a-zA-Z°]+)\s*", str(v))
        if not m:
            raise ValueError(f"Couldn’t parse quantity: {v!r}")
        val, unit = float(m[1]), m[2].lower()
        if unit in ("deg", "°"):
            return math.radians(val)
        factor = cls.UNIT_FACTORS.get(unit)
        if factor is None:
            raise ValueError(f"Unknown unit: {unit!r}")
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
    def check_range(cls, r):
        if r.max <= r.min:
            raise ValueError("Range end must be greater than start")
        return r

    @property
    def span(self) -> float:
        return float(self.max - self.min)


class QuantityRange[Q: Quantity](BaseModel):
    min: Q | float = Field(default=float("nan"), description="Minimum value of the range")
    max: Q | float = Field(default=float("nan"), description="Maximum value of the range")
    span: Q | float = Field(default=float("nan"), description="Span of the range")

    @model_validator(mode="after")
    def check_inputs(cls, r):
        if math.isnan(r.max) and not math.isnan(r.min) and not math.isnan(r.span):
            r.max = r.min + r.span
        elif math.isnan(r.min) and not math.isnan(r.max) and not math.isnan(r.span):
            r.min = r.max - r.span
        elif math.isnan(r.span) and not math.isnan(r.min) and not math.isnan(r.max):
            if r.max <= r.min:
                raise ValueError("Range end must be greater than start")
            r.span = r.max - r.min
        elif math.isnan(r.min) and math.isnan(r.max) and not math.isnan(r.span):
            raise ValueError("At least 'min' or 'max' must be provided if 'span' is given.")
        elif math.isnan(r.min) and math.isnan(r.max) and math.isnan(r.span):
            raise ValueError("At least two of 'min', 'max', or 'span' must be provided.")
        return r


class NormalizedRange(BaseModel):
    min: float = Field(default=float("nan"), ge=0.0)
    max: float = Field(default=float("nan"), le=1.0)
    span: float = Field(default=float("nan"), ge=0.0)

    @model_validator(mode="after")
    def check_range(cls, r):
        if math.isnan(r.max) and not math.isnan(r.min) and not math.isnan(r.span):
            r.max = r.min + r.span
        elif math.isnan(r.min) and not math.isnan(r.max) and not math.isnan(r.span):
            r.min = r.max - r.span
        elif math.isnan(r.span) and not math.isnan(r.min) and not math.isnan(r.max):
            if r.max <= r.min:
                raise ValueError("Range end must be greater than start")
            r.span = r.max - r.min
        elif math.isnan(r.min) and math.isnan(r.max) and not math.isnan(r.span):
            raise ValueError("At least 'min' or 'max' must be provided if 'span' is given.")
        elif math.isnan(r.min) and math.isnan(r.max) and math.isnan(r.span):
            r.min = 0.0
            r.max = 1.0
            r.span = 1.0
        return r


VoltageRange = QuantityRange[Voltage]
FrequencyRange = QuantityRange[Frequency]
AngleRange = QuantityRange[Angle]
TimeWindow = QuantityRange[Time]
