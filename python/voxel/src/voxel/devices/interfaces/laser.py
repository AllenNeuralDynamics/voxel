from abc import abstractmethod

from voxel.utils.descriptors.deliminated import deliminated_float

from ..base import VoxelDevice, VoxelDeviceType


class VoxelLaser(VoxelDevice):
    """Base class for all voxel laser devices."""

    def __init__(self, name: str, wavelength: int) -> None:
        self._wavelength = wavelength
        super().__init__(device_type=VoxelDeviceType.LASER, uid=name)

    def __repr__(self) -> str:
        return (
            f"voxel id:         {self.uid}\n"
            f"Wavelength:       {self.wavelength}\n"
            f"Power setpoint:   {self.power_setpoint_mw} mW\n"
            f"Power:            {self.power_mw} mW\n"
            f"Temperature:      {self.temperature_c} °C"
        )

    @abstractmethod
    def enable(self) -> None:
        """Turn on the laser"""
        pass

    @abstractmethod
    def disable(self) -> None:
        """Turn off the laser"""
        pass

    @property
    def wavelength(self) -> int:
        """Wavelength of laser"""
        return self._wavelength

    @deliminated_float()
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
    def power_setpoint_mw(self, value: float) -> None:
        """
        Set the power setpoint for the laser in mW.

        :param value: The power setpoint in mW.
        :type value: float
        :rtype: None
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
