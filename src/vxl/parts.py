"""The parts whose facts vxl reads: a filter and an objective. A rig file names them by their class, such as
``target: vxl.parts.Filter``."""

from typing import Annotated, Literal

from pydantic import AfterValidator, Field
from vxlib.units import Wavelength

from rigup import Part


def _check_band(band: tuple[Wavelength | None, Wavelength | None]) -> tuple[Wavelength | None, Wavelength | None]:
    low, high = band
    if low is None and high is None:
        raise ValueError("a band needs at least 1 end")
    if low is not None and high is not None and not low < high:
        raise ValueError(f"a band goes from low to high, got [{low}, {high}]")
    return band


PassBand = Annotated[tuple[Wavelength | None, Wavelength | None], AfterValidator(_check_band)]
"""The wavelengths that a part lets through, from low to high. ``null`` leaves an end open, as a long-pass filter
does."""

Magnification = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Filter(Part, frozen=True):
    """A part that lets 1 band of wavelengths through."""

    kind: Literal["filter"] = "filter"
    band: PassBand


class Objective(Part, frozen=True):
    """A part that magnifies. 1 objective can stand for the objective and its tube lens together."""

    kind: Literal["objective"] = "objective"
    magnification: Magnification
