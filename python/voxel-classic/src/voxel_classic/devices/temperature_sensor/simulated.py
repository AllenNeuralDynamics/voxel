import numpy
from voxel.utils.log import VoxelLogging
from voxel_classic.devices.temperature_sensor.base import BaseTemperatureSensor


class SimulatedTemperatureSensor(BaseTemperatureSensor):
    """Simulated temperature sensor for testing purposes."""

    def __init__(self, id: str, channel: str):
        """
        Initialize the SimulatedTemperatureSensor object.

        :param id: Sensor ID
        :type id: str
        :param channel: Sensor channel
        :type channel: str
        """
        self.log = VoxelLogging.get_logger(obj=self)
        self.id = id
        self.channel = channel

    def reset(self) -> None:
        """
        Reset the temperature sensor.
        """
        self.log.info("reseting temperature sensor")
        pass

    @property
    def channel(self) -> str:
        """
        Get the current channel.

        :return: Current channel
        :rtype: str
        """
        return self._channel

    @channel.setter
    def channel(self, channel: str) -> None:
        """
        Set the current channel.

        :param channel: Channel to set
        :type channel: str
        """
        self._channel = channel

    @property
    def relative_humidity_percent(self) -> float:
        """
        Get the relative humidity percentage.

        :return: Relative humidity percentage
        :rtype: float
        """
        return 40.0 + numpy.random.normal(0, 1)

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        return 23.0 + numpy.random.normal(0, 1)

    def close(self) -> None:
        """
        Close the temperature sensor.
        """
        self.log.info("closing temperature sensor")
        pass
