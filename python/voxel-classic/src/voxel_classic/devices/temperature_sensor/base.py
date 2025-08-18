from abc import abstractmethod

from voxel_classic.devices.base import BaseDevice


class BaseTemperatureSensor(BaseDevice):
    """Base class for temperature sensors."""

    def __init__(self, id: str, channel: str):
        """
        Initialize the BaseTemperatureSensor object.

        :param id: Sensor ID
        :type id: str
        :param channel: Sensor channel
        :type channel: str
        """
        super().__init__(id)

    @abstractmethod
    def reset(self) -> None:
        """
        Reset the temperature sensor.
        """
        pass

    @property
    @abstractmethod
    def channel(self) -> str:
        """
        Get the current channel.

        :return: Current channel
        :rtype: str
        """
        pass

    @channel.setter
    @abstractmethod
    def channel(self, channel: str) -> None:
        """
        Set the current channel.

        :param channel: Channel to set
        :type channel: str
        """
        pass

    @property
    @abstractmethod
    def relative_humidity_percent(self) -> float:
        """
        Get the relative humidity percentage.

        :return: Relative humidity percentage
        :rtype: float
        """
        pass

    @property
    @abstractmethod
    def temperature_c(self) -> float:
        """
        Get the temperature in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        pass

    def close(self) -> None:
        """
        Close the temperature sensor.
        """
        pass
