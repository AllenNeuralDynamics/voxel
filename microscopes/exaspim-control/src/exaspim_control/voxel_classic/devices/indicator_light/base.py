from abc import abstractmethod

from exaspim_control.voxel_classic.devices.base import BaseDevice


class BaseIndicatorLight(BaseDevice):
    """Base class for indicator light devices."""

    def __init__(self):
        """Initialization of the BaseIndicatorLight class."""

    @abstractmethod
    def enable(self) -> None:
        """Enable the indicator light."""

    @abstractmethod
    def disable(self) -> None:
        """Disable the indicator light."""

    @property
    @abstractmethod
    def settings(self) -> dict:
        """Get the active settings.

        :return: The active settings.
        :rtype: dict
        """

    @settings.setter
    @abstractmethod
    def settings(self, settings: dict) -> None:
        """Set the active settings.

        :param settings: Active settings.
        :type settings: dict
        """

    @abstractmethod
    def close(self) -> None:
        """Close the indicator light device."""
