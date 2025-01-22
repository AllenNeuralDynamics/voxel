"""
Module for a voxel lens device.
"""

from .base import VoxelDevice, VoxelDeviceType


class VoxelLens(VoxelDevice):
    """A voxel lens device.
    :param magnification: The magnification of the lens.
    :param name: The name of the lens.
    :param focal_length_um: The focal length of the lens in micrometers.
    :param aperture_um: The aperture of the lens in micrometers.
    :return lens: The lens device.
    :type magnification: float
    :type name: str | None
    :type focal_length_um: float| None
    :type aperture_um: float| None
    :rtype lens: VoxelLens
    """

    def __init__(
        self,
        magnification: float,
        name: str = "voxel_lens",
        focal_length_um: float | None = None,
        aperture_um: float | None = None,
    ):
        self.magnification = float(magnification)
        self.focal_length_um: float | None = focal_length_um
        self.aperture_um: float | None = aperture_um
        super().__init__(device_type=VoxelDeviceType.LENS, name=name)

    def close(self):
        """Close the lens."""
        pass
