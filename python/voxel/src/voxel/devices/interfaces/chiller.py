from abc import abstractmethod

from voxel.devices.base import VoxelDevice, VoxelDeviceType


class VoxelChiller(VoxelDevice):
    """Base class for voxel chillers."""

    def __init__(self, name: str) -> None:
        super().__init__(device_type=VoxelDeviceType.CHILLER, uid=name)

    @property
    @abstractmethod
    def temperature_c(self) -> float:
        """Get the current temperature of the chiller.

        :return: The current temperature of the chiller.
        :rtype: float
        """

    @temperature_c.setter
    @abstractmethod
    def temperature_c(self, value: float) -> None:
        """Set the temperature of the chiller.

        :param value: The temperature to set the chiller to.
        :type value: float
        """
