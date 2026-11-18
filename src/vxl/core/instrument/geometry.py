"""Where each camera's pixels land in the specimen: 1 frame, and 1 capture of frames as the stage runs.

Every position is in specimen µm. A stage position is where the center of each camera's sensor is. Array axes are
in z, y, x order, slowest first, as OME-Zarr stores them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

import numpy as np
from vxlib.vector import Span, Vec3D

from vxl.core.instrument.config import SpecimenAxis
from vxl.devices.camera import AreaROI, CameraSensor

_ZERO = Vec3D(z=0.0, y=0.0, x=0.0)


@dataclass(frozen=True)
class Transform:
    """Where each element of an array sits in the specimen. Element ``[i, j, k]`` is at
    ``origin + i * steps[0] + j * steps[1] + k * steps[2]``."""

    origin: Vec3D
    steps: tuple[Vec3D, Vec3D, Vec3D]
    shape: tuple[int, int, int]

    def position(self, index: Sequence[float]) -> Vec3D:
        """The specimen position of an index, 1 value for each array axis."""
        position = self.origin
        for i, step in zip(index, self.steps, strict=True):
            position = position + step * i
        return position

    def bounds(self) -> dict[SpecimenAxis, Span]:
        """The span on each specimen axis that holds every element, out to the outer edges of the first and last."""
        corners = [self.position(c) for c in product(*((-0.5, size - 0.5) for size in self.shape))]
        return {
            axis: Span(
                min(getattr(c, axis) for c in corners),
                max(getattr(c, axis) for c in corners),
            )
            for axis in ("z", "y", "x")
        }

    @classmethod
    def frame(cls, axes: tuple[Vec3D, Vec3D], sensor: CameraSensor, roi: AreaROI, *, binning: int = 1) -> "Transform":
        """The transform of 1 frame of a camera at stage position 0: an array of shape (1, y, x). ``axes`` gives where
        1 µm along the sensor's width and height lands in the specimen."""
        along_x, along_y = axes
        pixel, size = sensor.pixel_um, sensor.size_px
        x_step, y_step = along_x * (pixel.x * binning), along_y * (pixel.y * binning)
        nx, ny = roi.w // binning, max(roi.h // binning, 1)
        # How far the read-out region's center sits from the sensor's center.
        center = along_x * ((roi.x + roi.w / 2 - size.x / 2) * pixel.x) + along_y * (
            (roi.y + roi.h / 2 - size.y / 2) * pixel.y
        )
        origin = center - x_step * ((nx - 1) / 2) - y_step * ((ny - 1) / 2)
        return cls(origin, (_ZERO, y_step, x_step), (1, ny, nx))

    @property
    def matrix(self) -> np.ndarray:
        """The same as a 4 by 4 affine matrix, the form BigStitcher and OME-Zarr use. Its rows are z, y, x, then
        [0, 0, 0, 1]; its columns are the 3 steps, then the origin."""
        matrix = np.eye(4)
        matrix[:3, :] = np.column_stack([list(v) for v in (*self.steps, self.origin)])
        return matrix


@dataclass(frozen=True)
class AxisRun:
    """How the scan axis runs during a scan: ``count`` frames, ``spacing`` µm apart, from ``first`` µm. A sweep
    runs at ``speed`` µm/s; a step has none."""

    axis: SpecimenAxis
    first: float
    spacing: float
    count: int
    speed: float | None = None

    def transform(self, frame: "Transform", at: Vec3D) -> "Transform":
        """The transform of 1 capture of ``frame`` as the stage runs: from ``at`` on the other axes, and from
        ``first`` along ``axis``, ``count`` frames ``spacing`` µm apart. Array axis 0 is the run, so the frame must
        have 1 element there."""
        if frame.shape[0] != 1 or frame.steps[0] != _ZERO:
            raise ValueError(f"the frame has no free axis 0 for the scan along '{self.axis}'")
        start = Vec3D(**{axis: self.first if axis == self.axis else getattr(at, axis) for axis in ("z", "y", "x")})
        step = Vec3D(**{axis: self.spacing if axis == self.axis else 0.0 for axis in ("z", "y", "x")})
        return Transform(frame.origin + start, (step, frame.steps[1], frame.steps[2]), (self.count, *frame.shape[1:]))


__all__ = ["AxisRun", "Transform"]
