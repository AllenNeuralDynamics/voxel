from abc import abstractmethod

from voxel.devices.base import VoxelDevice


class BaseIndicatorLight(VoxelDevice):
    """
    Base class for indicator light devices.
    """

    def __init__(self):
        """Initialization of the BaseIndicatorLight class."""

    @property
    @abstractmethod
    def active_settings(self) -> dict:
        """
        Get the active settings.

        :return: The active settings.
        :rtype: dict
        """
        pass

    @active_settings.setter
    @abstractmethod
    def active_settings(self, value: dict) -> None:
        """
        Set the active settings.

        :param value: Active setings.
        :type value: dict
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the indicator light device.
        """
        pass
