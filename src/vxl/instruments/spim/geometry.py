"""Where each camera's pixels land in the specimen: 1 frame, 1 capture of frames, and what the cameras see around
the stage position.

Every position is in specimen µm. A stage position is where the center of each camera's sensor is. Array axes are
in z, y, x order, slowest first, as OME-Zarr stores them.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import product

import numpy as np
from vxlib.vector import Span, Vec3D

from vxl.core.instrument.config import Detector, DeviceUid, SpecimenAxis
from vxl.devices.camera import AreaROI, CameraSensor


@dataclass(frozen=True)
class AxisRun:
    """How the scan axis runs during a scan: ``count`` frames, ``spacing`` µm apart, from ``first`` µm. A sweep
    runs at ``speed`` µm/s; a step has none."""

    axis: SpecimenAxis
    first: float
    spacing: float
    count: int
    speed: float | None = None


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

    def scanned(self, first: Vec3D, scan: AxisRun) -> "Transform":
        """The transform of 1 capture of frames like this one, taken from stage position ``first`` as the stage
        moves by ``scan``. Array axis 0 is the scan, so the frame must have 1 element there."""
        if self.shape[0] != 1 or self.steps[0] != _ZERO:
            raise ValueError(f"the frame has no free axis 0 for the scan along '{scan.axis}'")
        step = Vec3D(**{axis: scan.spacing if axis == scan.axis else 0.0 for axis in ("z", "y", "x")})
        return Transform(self.origin + first, (step, self.steps[1], self.steps[2]), (scan.count, *self.shape[1:]))

    @property
    def matrix(self) -> np.ndarray:
        """The same as a 4 by 4 affine matrix, the form BigStitcher and OME-Zarr use. Its rows are z, y, x, then
        [0, 0, 0, 1]; its columns are the 3 steps, then the origin."""
        matrix = np.eye(4)
        matrix[:3, :] = np.column_stack([list(v) for v in (*self.steps, self.origin)])
        return matrix


def frame_transform(
    detector: Detector,
    sensor: CameraSensor,
    roi: AreaROI,
    *,
    binning: int,
    magnification: float,
) -> Transform:
    """The transform of 1 saved frame of a camera at stage position 0: an array of shape (1, y, x). ``detector``
    gives the specimen directions of the frame's sides."""
    along_x, along_y = (side / magnification for side in detector.sides())
    pixel, size = sensor.pixel_um, sensor.size_px

    x_step, y_step = along_x * (pixel.x * binning), along_y * (pixel.y * binning)
    nx, ny = roi.w // binning, max(roi.h // binning, 1)
    # How far the read-out region's center sits from the sensor's center.
    center = along_x * ((roi.x + roi.w / 2 - size.x / 2) * pixel.x) + along_y * (
        (roi.y + roi.h / 2 - size.y / 2) * pixel.y
    )
    origin = center - x_step * ((nx - 1) / 2) - y_step * ((ny - 1) / 2)
    return Transform(origin, (_ZERO, y_step, x_step), (1, ny, nx))


def footprint(frames: Mapping[DeviceUid, "Transform"]) -> dict[SpecimenAxis, Span]:
    """The span on each axis that some camera sees, around the stage position."""
    seen = [frame.bounds() for frame in frames.values()]
    return {axis: Span(min(s[axis].low for s in seen), max(s[axis].high for s in seen)) for axis in ("z", "y", "x")}


__all__ = ["AxisRun", "Transform", "footprint", "frame_transform"]
