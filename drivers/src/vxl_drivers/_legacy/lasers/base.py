from abc import abstractmethod

from rigup.device import Device
from rigup.interface import action, fact, failsafe, number, stream


class Laser(Device, kind="laser_archived"):
    """Legacy laser interface, discoverable separately from canonical lasers."""

    def __init__(self, uid: str, wavelength: int) -> None:
        self._wavelength = wavelength
        super().__init__(uid=uid)

    @property
    @fact(label="Wavelength", units="nm", desc="The wavelength of the laser.")
    def wavelength(self) -> int:
        """Get the wavelength of the laser in nm."""
        return self._wavelength

    @abstractmethod
    @action(label="Enable", desc="Turn on the laser.")
    def enable(self) -> None:
        """Turn on the laser."""

    @abstractmethod
    @failsafe(label="Disable", desc="Turn off the laser.")
    def disable(self) -> None:
        """Turn off the laser."""

    @property
    @abstractmethod
    @stream(label="Enabled", desc="Whether the laser is currently enabled.")
    def is_enabled(self) -> bool:
        """Check if the laser is enabled."""

    @property
    @abstractmethod
    @stream("fast", label="Power", units="mW", desc="Measured laser output power.")
    def power(self) -> float:
        """Get the measured laser output power."""

    @number()
    @abstractmethod
    @stream("fast", label="Power Setpoint", units="mW", desc="Commanded laser power.")
    def power_setpoint(self) -> float:
        """Get the commanded laser power setpoint."""

    @power_setpoint.setter
    @abstractmethod
    def power_setpoint(self, value: float) -> None:
        """Command the laser to a new power setpoint."""

    @property
    @abstractmethod
    @stream("slow", label="Temperature", units="°C", desc="The temperature of the laser.")
    def temperature_c(self) -> float | None:
        """Get the temperature of the laser in degrees Celsius."""
