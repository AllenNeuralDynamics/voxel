from abc import abstractmethod

from rigup import Device, describe, numeric
from vxl.device import DeviceType


class Laser(Device):
    __DEVICE_TYPE__ = DeviceType.LASER

    def __init__(self, uid: str, wavelength: int) -> None:
        self._wavelength = wavelength
        super().__init__(uid=uid)

    @property
    @describe(label="Wavelength", units="nm", desc="The wavelength of the laser.")
    def wavelength(self) -> int:
        """Get the wavelength of the laser in nm."""
        return self._wavelength

    @abstractmethod
    @describe(label="Enable", desc="Turn on the laser.")
    def enable(self) -> None:
        """Turn on the laser."""

    @abstractmethod
    @describe(label="Disable", desc="Turn off the laser.")
    def disable(self) -> None:
        """Turn off the laser."""

    @property
    @abstractmethod
    @describe(label="Enabled", desc="Whether the laser is currently enabled.", stream=True)
    def is_enabled(self) -> bool:
        """Check if the laser is enabled."""

    @property
    @abstractmethod
    @describe(label="Power", desc="Measured laser output power.", stream=True)
    def power(self) -> float:
        """Get the measured laser output power."""

    @numeric()
    @abstractmethod
    @describe(label="Power Setpoint", desc="Commanded laser power.", stream=True)
    def power_setpoint(self) -> float:
        """Get the commanded laser power setpoint."""

    @power_setpoint.setter
    @abstractmethod
    def power_setpoint(self, value: float) -> None:
        """Command the laser to a new power setpoint."""

    @property
    @abstractmethod
    @describe(label="Temperature", units="°C", desc="The temperature of the laser.")
    def temperature_c(self) -> float | None:
        """Get the temperature of the laser in degrees Celsius."""
