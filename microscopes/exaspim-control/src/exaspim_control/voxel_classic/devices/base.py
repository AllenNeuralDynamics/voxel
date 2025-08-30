"""Base class for all voxel devices."""

from abc import ABC, abstractmethod

from voxel.utils.log import VoxelLogging


class BaseDevice(ABC):
    """Base class for all voxel devices."""

    def __init__(self, uid: str) -> None:
        """
        Initialize the VoxelDevice object.

        :param id: Device ID
        :type id: str
        """
        self._uid = uid
        self.log = VoxelLogging.get_logger(obj=self)

    @property
    def uid(self) -> str:
        """
        Get the unique identifier for the device.

        :return: Device UID
        :rtype: str
        """
        return self._uid

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
        return f'{self.__class__.__name__}[{self.uid}]'
