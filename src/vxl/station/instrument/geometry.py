"""Where each camera's pixels land in the specimen: 1 frame, and 1 capture of frames as the stage runs. The
:class:`~vxlib.vector.Transform` of each holds the answer.

Every position is in specimen µm. A stage position is where the center of each camera's sensor is. Array axes are
in z, y, x order, slowest first, as OME-Zarr stores them.
"""

from dataclasses import dataclass

from vxlib.vector import Transform, Vec3D

from vxl.devices.camera import AreaROI, CameraSensor
from vxl.station.instrument.config import SpecimenAxis

_ZERO = Vec3D(z=0.0, y=0.0, x=0.0)


def camera_frame(axes: tuple[Vec3D, Vec3D], sensor: CameraSensor, roi: AreaROI, *, binning: int = 1) -> Transform:
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
    return Transform(origin, (_ZERO, y_step, x_step), (1, ny, nx))


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
