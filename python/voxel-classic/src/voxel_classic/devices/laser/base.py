from abc import abstractmethod

from voxel_classic.devices.base import BaseDevice

# map of wavelength ranges to color
WAVELENGTH_COLOR_MAP = {
    (400, 450): "violet",
    (450, 495): "blue",
    (495, 570): "green",
    (570, 590): "yellow",
    (590, 620): "orange",
    (620, 750): "red",
}


class BaseLaser(BaseDevice):
    """Base class for all voxel laser devices."""

    def __init__(self, uid: str) -> None:
        """
        Initialize the BaseLaser object.

        :param id: Laser ID
        :type id: str
        """
        super().__init__(uid)

    @abstractmethod
    def enable(self) -> None:
        """
        Turn on the laser.
        """
        pass

    @abstractmethod
    def disable(self) -> None:
        """
        Turn off the laser.
        """
        pass

    @property
    @abstractmethod
    def wavelength(self) -> int:
        """
        Get the wavelength of the laser.

        :return: Wavelength of the laser
        :rtype: int
        """
        pass

    @property
    def color(self) -> str:
        """
        Get the color of the laser based on its wavelength.

        :return: Color of the laser
        :rtype: str
        """
        for (start, end), color in WAVELENGTH_COLOR_MAP.items():
            if start <= self.wavelength < end:
                return color
        return "unknown"

    @property
    @abstractmethod
    def power_setpoint_mw(self) -> float:
        """
        The power setpoint is the target power that the laser is trying to achieve.

        :return: The power setpoint in mW.
        :rtype: float
        """
        pass

    @power_setpoint_mw.setter
    @abstractmethod
    def power_setpoint_mw(self, power_setpoint_mw: float) -> None:
        """
        Set the power setpoint for the laser in mW.

        :param power_setpoint_mw: The power setpoint in mW.
        """
        pass

    @property
    @abstractmethod
    def power_mw(self) -> float:
        """
        Get the actual power of the laser in mW.

        :return: The power in mW.
        :rtype: float
        """
        pass

    @property
    @abstractmethod
    def temperature_c(self) -> float | None:
        """
        Get the main temperature of the laser in degrees Celsius.

        :return: The temperature in degrees Celsius.
        :rtype: float
        """
        pass
