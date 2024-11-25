"""
Module for a voxel lens device.
"""

from typing import Optional

from .base import VoxelDevice, VoxelDeviceType


class VoxelLens(VoxelDevice):
    """A voxel lens device.
    :param magnification: The magnification of the lens.
    :param name: The name of the lens.
    :param focal_length_um: The focal length of the lens in micrometers.
    :param aperture_um: The aperture of the lens in micrometers.
    :return lens: The lens device.
    :type magnification: float
    :type name: Optional[str]
    :type focal_length_um: Optional[float]
    :type aperture_um: Optional[float]
    :rtype lens: VoxelLens
    """

    def __init__(
        self,
        magnification: float,
        name: str | None = None,
        focal_length_um: float | None = None,
        aperture_um: float | None = None,
    ):
        super().__init__(device_type=VoxelDeviceType.LENS, name=name)
        self.magnification = float(magnification)
        self.focal_length_um: float | None = focal_length_um
        self.aperture_um: float | None = aperture_um

    def close(self):
        """Close the lens."""
        pass
