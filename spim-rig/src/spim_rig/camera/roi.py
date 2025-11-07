from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ROIError(ValueError): ...


class ROIShapeError(ROIError): ...


class ROIBoundsError(ROIError): ...


class ROIGridError(ROIError): ...


class ROIPlacementError(ROIError): ...


class ROIAlignmentPolicy(StrEnum):
    """Defines how to handle invalid ROI configurations.

    - ALIGN: Adjust the ROI to the nearest valid configuration that aligns to grid.
    - CLIP: Clamp the ROI to the valid range then align to grid.
    - STRICT: Raise an error on invalid ROI.
    """

    ALIGN = "align"
    CLIP = "clip"
    STRICT = "strict"


class ROIConstraints(BaseModel):
    grid_x: int = Field(..., description="Grid alignment in X")
    grid_y: int = Field(..., description="Grid alignment in Y")
    min_x: int = Field(..., description="Minimum ROI width in pixels")
    min_y: int = Field(..., description="Minimum ROI height in pixels")
    max_w: int = Field(..., description="Maximum ROI width in pixels")
    max_h: int = Field(..., description="Maximum ROI height in pixels")

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def validate_constraints(self) -> ROIConstraints:
        if self.grid_x <= 0 or self.grid_y <= 0:
            raise ROIError("Grid must be >= 1.")
        if self.min_x <= 0 or self.min_y <= 0:
            raise ROIError("Minimum sizes must be > 0.")
        if self.min_x > self.max_w or self.min_y > self.max_h:
            raise ROIError("Min size exceeds max/sensor size.")
        return self


class Rectangle(BaseModel):
    x: int = Field(..., description="X coordinate")
    y: int = Field(..., description="Y coordinate")
    w: int = Field(..., description="Width")
    h: int = Field(..., description="Height")

    model_config = {"frozen": True}


class ROI(Rectangle):
    pass


def assert_positive_size(r: ROI) -> None:
    if r.w <= 0 or r.h <= 0:
        raise ROIShapeError("ROI width/height must be > 0.")


def assert_within_bounds(r: ROI, w: int, h: int) -> None:
    if r.x < 0 or r.y < 0 or r.x + r.w > w or r.y + r.h > h:
        raise ROIBoundsError("ROI is out of bounds.")


def assert_min_size(r: ROI, min_w: int, min_h: int) -> None:
    if r.w < min_w or r.h < min_h:
        err = f"ROI smaller than minimum ({min_w}x{min_h})."
        raise ROIBoundsError(err)


def assert_on_grid(r: ROI, gx: int, gy: int) -> None:
    if (r.x % gx) or (r.w % gx) or (r.y % gy) or (r.h % gy):
        err = f"ROI not aligned to grid ({gx},{gy})."
        raise ROIGridError(err)


def validate_strict(r: ROI, caps: ROIConstraints) -> None:
    """All invariants that must hold for a legal ROI right now."""
    assert_positive_size(r)
    assert_within_bounds(r, caps.max_w, caps.max_h)
    assert_min_size(r, caps.min_x, caps.min_y)
    assert_on_grid(r, caps.grid_x, caps.grid_y)


def coerce_roi(r: ROI, caps: ROIConstraints, policy: ROIAlignmentPolicy) -> ROI:
    gx, gy = caps.grid_x or 1, caps.grid_y or 1

    if policy is ROIAlignmentPolicy.STRICT:
        validate_strict(r, caps)
        return r

    # 1) start rectangle
    if policy is ROIAlignmentPolicy.CLIP:
        x = min(max(r.x, 0), caps.max_w)
        y = min(max(r.y, 0), caps.max_h)
        rw = min(max(r.w, caps.min_x), caps.max_w - x)
        rh = min(max(r.h, caps.min_y), caps.max_h - y)
    else:  # ALIGN
        x, y, rw, rh = r.x, r.y, r.w, r.h

    # 2) snap to grid and min
    x -= x % gx
    y -= y % gy
    rw -= rw % gx
    rh -= rh % gy
    if rw < caps.min_x:
        rw = ((caps.min_x + gx - 1) // gx) * gx
    if rh < caps.min_y:
        rh = ((caps.min_y + gy - 1) // gy) * gy

    # 3) ensure inside bounds
    if x + rw > caps.max_w:
        x = max(0, (caps.max_w - rw) - ((caps.max_w - rw) % gx))
    if y + rh > caps.max_h:
        y = max(0, (caps.max_h - rh) - ((caps.max_h - rh) % gy))

    eff = ROI(x=x, y=y, w=rw, h=rh)
    try:
        validate_strict(eff, caps)
    except ROIError as e:
        raise ROIPlacementError("ROI cannot be placed with given constraints") from e
    return eff
