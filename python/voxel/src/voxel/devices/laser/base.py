from abc import abstractmethod

from voxel.devices.device import VoxelDevice, VoxelDeviceType
from voxel.utils.descriptors.deliminated import deliminated_float


class VoxelLaser(VoxelDevice):
    """Base class for all voxel laser devices."""

    def __init__(self, uid: str, wavelength: int) -> None:
        self._wavelength = wavelength
        super().__init__(device_type=VoxelDeviceType.LASER, uid=uid)

    def __repr__(self) -> str:
        return (
            f'voxel id:         {self.uid}\n'
            f'Wavelength:       {self.wavelength}\n'
            f'Power setpoint:   {self.power_setpoint_mw} mW\n'
            f'Power:            {self.power_mw} mW\n'
            f'Temperature:      {self.temperature_c} °C'
        )

    @abstractmethod
    def enable(self) -> None:
        """Turn on the laser."""

    @abstractmethod
    def disable(self) -> None:
        """Turn off the laser."""

    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if the laser is enabled."""

    @property
    def wavelength(self) -> int:
        """Wavelength of laser."""
        return self._wavelength

    @deliminated_float()
    @abstractmethod
    def power_setpoint_mw(self) -> float:
        """The power setpoint is the target power that the laser is trying to achieve.

        :return: The power setpoint in mW.
        :rtype: float
        """

    @power_setpoint_mw.setter
    @abstractmethod
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint for the laser in mW.

        :param value: The power setpoint in mW.
        :type value: float
        :rtype: None
        """

    @property
    @abstractmethod
    def power_mw(self) -> float:
        """Get the actual power of the laser in mW.

        :return: The power in mW.
        :rtype: float
        """

    @property
    @abstractmethod
    def temperature_c(self) -> float | None:
        """Get the main temperature of the laser in degrees Celsius.

        :return: The temperature in degrees Celsius.
        :rtype: float
        """
