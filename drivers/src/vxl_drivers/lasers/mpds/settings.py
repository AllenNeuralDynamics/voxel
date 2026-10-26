"""MPDS operating settings with optional RF-dBm to optical-percent calibration.

Source wavelength remains authoritative. Calibration metadata describes the setup
used for measurement; mismatches are warnings issued by the composed laser.
"""

from itertools import pairwise
from math import isclose
from typing import Literal, Self

from numpy.polynomial import Polynomial
from pydantic import Field, FiniteFloat, model_validator
from vxlib.calibration import CalibrationModel, PiecewiseLinearCalibration
from vxlib.schema import FrozenModel


class MPDSCalibration(FrozenModel):
    """A normalized optical response and the conditions under which it was measured."""

    version: Literal[1] = 1
    wavelength_nm: FiniteFloat = Field(gt=0)
    source_reference_mw: FiniteFloat = Field(gt=0)
    measured_full_scale_mw: FiniteFloat = Field(gt=0)
    mapping: CalibrationModel


class MPDSSettings(FrozenModel):
    """One RF operating interval; omit calibration for normalized RF control."""

    frequency_mhz: FiniteFloat = Field(gt=0)
    min_rf_power_dbm: FiniteFloat = Field(default=0, ge=0)
    max_rf_power_dbm: FiniteFloat = Field(ge=0)
    calibration: MPDSCalibration | None = None

    @model_validator(mode="after")
    def _validate_operating_interval(self) -> Self:
        lower, upper = self.min_rf_power_dbm, self.max_rf_power_dbm
        if lower >= upper:
            raise ValueError("RF power limits must be increasing")
        if any(not isclose(value, round(value, 1), rel_tol=0, abs_tol=1e-9) for value in (lower, upper)):
            raise ValueError("RF power limits must use 0.1 dBm increments")
        if not isclose(self.frequency_mhz, round(self.frequency_mhz, 3), rel_tol=0, abs_tol=1e-9):
            raise ValueError("RF frequency must use 0.001 MHz increments")
        if self.calibration is None:
            return self
        mapping = self.calibration.mapping
        if mapping.domain[0] > lower or mapping.domain[1] < upper:
            raise ValueError("calibration domain must cover the RF operating interval")
        # Analyze a restricted copy so inversions cannot select roots outside the operating interval.
        restricted = mapping.model_copy(update={"domain": (lower, upper)})
        validate_monotonic(restricted)
        endpoints = (restricted.forward(lower), restricted.forward(upper))
        if min(endpoints) < 0 or not isclose(max(endpoints), 100, rel_tol=0, abs_tol=1e-6):
            raise ValueError("calibrated output must run from a nonnegative percentage to 100%")
        return self

    @property
    def minimum_level_percent(self) -> float:
        if self.calibration is None:
            return 0.0
        mapping = self.calibration.mapping
        return min(mapping.forward(self.min_rf_power_dbm), mapping.forward(self.max_rf_power_dbm))

    def rf_power(self, level: float) -> float:
        """Map an operating percentage to an in-range command on the controller's RF grid."""
        if not self.minimum_level_percent <= level <= 100:
            raise ValueError("output level is outside the supported operating range")
        lower, upper = self.min_rf_power_dbm, self.max_rf_power_dbm
        if self.calibration is None:
            power = lower + level / 100 * (upper - lower)
        else:
            mapping = self.calibration.mapping.model_copy(update={"domain": (lower, upper)})
            # Endpoint values may differ from 100 by numerical fitting tolerance.
            power = max((lower, upper), key=mapping.forward) if level == 100 else mapping.inverse(level)
        return min(upper, max(lower, round(power, 1)))


def validate_monotonic(mapping: CalibrationModel) -> None:
    """Require a strictly monotonic response on the domain, allowing isolated flat tangents."""
    lower, upper = mapping.domain
    if isinstance(mapping, PiecewiseLinearCalibration):
        knots = [lower, *(x for x, _ in mapping.points if lower < x < upper), upper]
        values = [mapping.forward(x) for x in knots]
        changes = [b - a for a, b in pairwise(values)]
    else:
        derivative = Polynomial(mapping.coefficients).deriv().trim()
        roots = [
            float(root.real) for root in derivative.roots() if abs(root.imag) <= 1e-9 and lower < root.real < upper
        ]
        knots = [lower, *sorted(set(roots)), upper]
        changes = [float(derivative((a + b) / 2)) for a, b in pairwise(knots)]
    if not (all(value > 0 for value in changes) or all(value < 0 for value in changes)):
        raise ValueError("calibration must be strictly monotonic over the RF operating interval")
