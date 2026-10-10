"""Bounded scalar calibrations with explicit inverse-solution selection.

PolynomialCalibration and PiecewiseLinearCalibration are immutable Pydantic models
backed by NumPy. Units, physical limits, and hardware rounding belong to the caller;
evaluation and inversion are bounded by each model's domain.

Example::

    calibration = PolynomialCalibration(coefficients=(0, 2, 0.01), domain=(0, 100))
    output = calibration.forward(40)
    setting = calibration.inverse(output)

    fitted = PolynomialCalibration.fit(((0, 0), (20, 44), (40, 96)), degree=2)
    sampled = PiecewiseLinearCalibration(points=((0, 0), (20, 44), (40, 96)), domain=(0, 40))

Serialize with model_dump() / model_dump_json(); restore with the concrete class's
model_validate() / model_validate_json(). Constructors accept sequences and retain
immutable tuples. Use model_dump(mode="json") for YAML-compatible lists and numbers.
CalibrationModel accepts either model in configuration fields, discriminated by
kind ("polynomial" or "piecewise_linear"). Parse standalone mappings with
calibration_adapter.validate_python(data).
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from math import isfinite
from typing import Annotated, Literal, NamedTuple, Self

import numpy as np
from numpy.polynomial import Polynomial
from pydantic import Field, FiniteFloat, TypeAdapter, model_validator

from vxlib.schema import FrozenModel

type InverseStrategy = Literal["unique", "lowest", "highest", "nearest"]


class NoSolutionError(ValueError):
    """The requested output has no solution in the operating interval."""


class AmbiguousSolutionError(ValueError):
    """The requested selection does not identify one input."""


class SolutionInterval(NamedTuple):
    """A closed solution interval; equal endpoints represent a single input."""

    lower: float
    upper: float


class Calibration(FrozenModel, ABC):
    """A scalar relationship restricted to a finite, closed input interval.

    Tolerances are absolute in their respective input/output units and describe
    numerical acceptance, not measurement uncertainty. Inversion checks candidate
    inputs and output residuals; a root just outside the domain may be snapped to
    an endpoint only when both tolerances permit it. No extrapolation is performed.
    """

    domain: tuple[FiniteFloat, FiniteFloat]
    """Allowed input interval, including both endpoints."""

    input_tolerance: FiniteFloat = Field(default=1e-7, ge=0)
    """Absolute input tolerance for roots, duplicate solutions, and distance ties."""

    output_tolerance: FiniteFloat = Field(default=1e-9, ge=0)
    """Absolute output tolerance for accepting an inverse solution."""

    @model_validator(mode="after")
    def _validate_domain(self) -> Self:
        if self.domain[0] >= self.domain[1]:
            raise ValueError("domain must have a lower bound strictly below its upper bound")
        return self

    def forward(self, value: float) -> float:
        """Evaluate an input in the domain; out-of-domain inputs raise ValueError."""
        _finite(value, "input")
        if not self.domain[0] <= value <= self.domain[1]:
            raise ValueError(f"input {value} is outside domain {self.domain}")
        result = self._evaluate(value)
        _finite(result, "calculated output")
        return result

    def solutions(self, value: float) -> tuple[SolutionInterval, ...]:
        """Return sorted inverse-solution intervals; an empty tuple means none.

        Equal endpoints identify a single input; distinct endpoints describe a
        flat interval. Overlapping intervals merge. Input tolerance deduplicates
        nearby point solutions but never joins gaps between flat intervals.
        """
        _finite(value, "output")
        merged: list[SolutionInterval] = []
        for interval in sorted(self._solve(value)):
            if merged and interval.lower <= merged[-1].upper:
                previous = merged.pop()
                merged.append(SolutionInterval(previous.lower, max(previous.upper, interval.upper)))
            elif (
                merged
                and interval.lower == interval.upper
                and merged[-1].lower == merged[-1].upper
                and interval.lower - merged[-1].upper <= self.input_tolerance
            ):
                continue
            else:
                merged.append(interval)
        return tuple(merged)

    def inverse(
        self,
        value: float,
        *,
        strategy: InverseStrategy = "unique",
        reference: float | None = None,
    ) -> float:
        """Select an input in the domain; raise NoSolutionError if none exists.

        The default "unique" strategy rejects multiple inputs with
        AmbiguousSolutionError. "lowest" and "highest" select the corresponding
        endpoint. "nearest" requires an explicit reference and rejects ties within
        input_tolerance. On a flat interval it returns the reference when inside,
        or the closest endpoint otherwise. Previous settings are not tracked and
        branch continuity is not guaranteed.
        """
        if strategy not in {"unique", "lowest", "highest", "nearest"}:
            raise ValueError(f"unknown inverse strategy: {strategy!r}")
        if strategy == "nearest":
            if reference is None:
                raise ValueError("nearest requires an explicit reference")
            _finite(reference, "reference")
        elif reference is not None:
            raise ValueError("reference is only valid with the nearest strategy")

        intervals = self.solutions(value)
        if not intervals:
            raise NoSolutionError(f"no solution for output {value} in domain {self.domain}")
        if strategy == "lowest":
            return intervals[0].lower
        if strategy == "highest":
            return intervals[-1].upper
        if strategy == "nearest" and reference is not None:
            candidates = [min(max(reference, interval.lower), interval.upper) for interval in intervals]
            distances = [abs(candidate - reference) for candidate in candidates]
            closest = min(distances)
            selected = [
                candidate
                for candidate, distance in zip(candidates, distances, strict=True)
                if distance - closest <= self.input_tolerance
            ]
            if len(selected) == 1:
                return selected[0]
            raise AmbiguousSolutionError("multiple solutions are equally near the reference")
        if len(intervals) == 1 and intervals[0].lower == intervals[0].upper:
            return intervals[0].lower
        raise AmbiguousSolutionError(f"output {value} has multiple inputs in domain {self.domain}")

    @abstractmethod
    def _evaluate(self, value: float) -> float: ...

    @abstractmethod
    def _solve(self, value: float) -> list[SolutionInterval]: ...


class PolynomialCalibration(Calibration):
    """A polynomial with coefficients ordered from constant to highest power.

    Numerical inversion can lose accuracy with high degree, repeated roots, or
    poorly scaled coefficients. A repeated root may appear as several nearby
    candidates or be rejected when its numerical error exceeds the tolerances.
    Choose tolerances for the units and precision of the calibration.
    """

    kind: Literal["polynomial"] = "polynomial"
    coefficients: tuple[FiniteFloat, ...] = Field(min_length=1)
    """For example, (1, 2, 3) represents 1 + 2*x + 3*x**2."""

    def _evaluate(self, value: float) -> float:
        return float(Polynomial(self.coefficients)(value))

    def _solve(self, value: float) -> list[SolutionInterval]:
        polynomial = Polynomial(self.coefficients).trim()
        if polynomial.degree() == 0:
            if abs(float(polynomial.coef[0]) - value) <= self.output_tolerance:
                return [SolutionInterval(*self.domain)]
            return []

        candidates: list[float] = []
        for root in (polynomial - value).convert(domain=self.domain).roots():
            if abs(float(np.imag(root))) <= self.input_tolerance:
                candidates.append(float(np.real(root)))
        # Include boundary roots even when numerical root finding puts them just outside.
        candidates.extend(self.domain)
        solutions: list[SolutionInterval] = []
        for root in sorted(candidates):
            if not isfinite(root):
                continue
            lower, upper = self.domain
            if root < lower - self.input_tolerance or root > upper + self.input_tolerance:
                continue
            candidate = min(max(root, lower), upper)
            if abs(self.forward(candidate) - value) > self.output_tolerance:
                continue
            if solutions and candidate - solutions[-1].lower <= self.input_tolerance:
                continue
            solutions.append(SolutionInterval(candidate, candidate))
        return solutions

    @classmethod
    def fit(
        cls,
        points: Sequence[tuple[float, float]],
        *,
        degree: int,
        domain: tuple[float, float] | None = None,
        input_tolerance: float = 1e-7,
        output_tolerance: float = 1e-9,
    ) -> Self:
        """Estimate coefficients by least squares; reject rank-deficient fits.

        The domain defaults to the sample extent; an explicit domain may narrow it.
        Unlike interpolation, the fitted polynomial need not pass through samples.
        """
        if isinstance(degree, bool) or not isinstance(degree, int) or degree < 0:
            raise ValueError("degree must be a non-negative integer")
        if len(points) < max(2, degree + 1):
            raise ValueError("fit needs at least two samples and degree + 1 samples")
        x, y = zip(*points, strict=True)
        for value in (*x, *y):
            _finite(value, "sample")
        if len(set(x)) < max(2, degree + 1):
            raise ValueError("fit needs at least two distinct inputs and degree + 1 distinct inputs")
        sample_domain = (min(x), max(x))
        if domain is not None and (domain[0] < sample_domain[0] or domain[1] > sample_domain[1]):
            raise ValueError("fit domain must lie within the sample extent")
        fitted, diagnostics = Polynomial.fit(x, y, degree, full=True)
        if diagnostics[1] != degree + 1:
            raise ValueError("polynomial fit is rank deficient; use a lower degree")
        return cls(
            coefficients=tuple(float(coefficient) for coefficient in fitted.convert().coef),
            domain=sample_domain if domain is None else domain,
            input_tolerance=input_tolerance,
            output_tolerance=output_tolerance,
        )


class PiecewiseLinearCalibration(Calibration):
    """Interpolate samples with strictly increasing inputs, passing through each point.

    Outputs may increase, decrease, or remain flat. The domain must lie within
    the sample extent; extrapolation is not supported.
    """

    kind: Literal["piecewise_linear"] = "piecewise_linear"
    points: tuple[tuple[FiniteFloat, FiniteFloat], ...] = Field(min_length=2)
    """Input/output pairs in strictly increasing input order."""

    @model_validator(mode="after")
    def _validate_points(self) -> Self:
        if any(left[0] >= right[0] for left, right in zip(self.points, self.points[1:], strict=False)):
            raise ValueError("sample inputs must be strictly increasing")
        if self.domain[0] < self.points[0][0] or self.domain[1] > self.points[-1][0]:
            raise ValueError("domain must lie within the sample extent")
        return self

    def _evaluate(self, value: float) -> float:
        x, y = zip(*self.points, strict=True)
        return float(np.interp(value, x, y))

    def _solve(self, value: float) -> list[SolutionInterval]:
        solutions: list[SolutionInterval] = []
        for (x0, y0), (x1, y1) in zip(self.points, self.points[1:], strict=False):
            lower, upper = max(x0, self.domain[0]), min(x1, self.domain[1])
            if lower > upper:
                continue
            if y0 == y1:
                if abs(value - y0) <= self.output_tolerance:
                    solutions.append(SolutionInterval(lower, upper))
                continue
            candidate = x0 + (value - y0) / (y1 - y0) * (x1 - x0)
            if candidate < lower - self.input_tolerance or candidate > upper + self.input_tolerance:
                continue
            candidate = min(max(candidate, lower), upper)
            if abs(self.forward(candidate) - value) <= self.output_tolerance:
                solutions.append(SolutionInterval(candidate, candidate))
        return solutions


type CalibrationModel = Annotated[
    PolynomialCalibration | PiecewiseLinearCalibration,
    Field(discriminator="kind"),
]

calibration_adapter = TypeAdapter(CalibrationModel)


def _finite(value: float, name: str) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")
