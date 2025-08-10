"""Base class for all voxel devices."""

from abc import ABC, abstractmethod

from voxel.utils.log import VoxelLogging


class VoxelDevice(ABC):
    """Base class for all voxel devices."""

    def __init__(self, id: str) -> None:
        """
        Initialize the VoxelDevice object.

        :param id: Device ID
        :type id: str
        """
        self.id = id
        self.log = VoxelLogging.get_logger(object=self)

    @abstractmethod
    def close(self) -> None:
        """
        Close the device.
        """
        pass

    def __str__(self) -> str:
        """
        Return a string representation of the device.

        :return: String representation of the device
        :rtype: str
        """
        return f"{self.__class__.__name__}[{self.id}]"
