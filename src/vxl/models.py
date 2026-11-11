"""Models that a device and an instrument file both use.

A model that only a device uses stays with that device. A model that only a file uses stays with that file's models.
"""

from typing import Annotated

from pydantic import BaseModel, Field
from vxlib.schema import FrozenModel

# === Axis positions ===

type AxisPosition = Annotated[float, Field(allow_inf_nan=False)] | str
"""Where an axis is: a number, or the name of a position for an axis that has named positions."""


# === Camera regions ===
# The part of a camera sensor that is read out. Every value is in sensor pixels before binning, so a region does not
# change when the binning does.


class IntRange(BaseModel):
    """Integer range with min, max, and step."""

    min: int
    max: int
    step: int = 1


class ROIGrid(BaseModel):
    """Hardware constraints for sensor ROI, one range per axis.

    Each axis describes valid sizes (width/height) with min, max, and step.
    Offset constraints are derived: min=0, max=axis.max - snapped_size, same step.
    """

    h: IntRange  # horizontal: valid widths
    v: IntRange  # vertical: valid heights


def _snap(value: int, r: IntRange) -> int:
    value = max(r.min, min(value, r.max))
    remainder = (value - r.min) % r.step
    if remainder != 0:
        value = value - remainder if remainder < r.step / 2 else value + (r.step - remainder)
    return min(value, r.max)


class AreaROI(FrozenModel):
    """The region of an area camera's sensor that is read out."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)

    def snap(self, grid: ROIGrid) -> "AreaROI":
        """Return a new region clamped and aligned to the given grid.

        Snaps size first, then derives offset bounds from the snapped size.
        """
        w = _snap(self.w, grid.h)
        h = _snap(self.h, grid.v)
        x = _snap(self.x, IntRange(min=0, max=grid.h.max - w, step=grid.h.step))
        y = _snap(self.y, IntRange(min=0, max=grid.v.max - h, step=grid.v.step))
        return AreaROI(x=x, y=y, w=w, h=h)


class LineROI(FrozenModel):
    """The pixels of a line camera's sensor that are read out."""

    x: int = Field(ge=0)
    w: int = Field(gt=0)


type CameraROI = AreaROI | LineROI

__all__ = ["AreaROI", "AxisPosition", "CameraROI", "IntRange", "LineROI", "ROIGrid"]
