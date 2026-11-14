from abc import abstractmethod

from rigup.device import Device, action, failsafe, number, prop


class Laser(Device, kind="laser_legacy"):
    """Legacy laser interface, discoverable separately from canonical lasers."""

    def __init__(self, uid: str, wavelength: int) -> None:
        self._wavelength = wavelength
        super().__init__(uid=uid)

    @property
    @prop(label="Wavelength", units="nm", desc="The wavelength of the laser.")
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
    @prop(label="Enabled", desc="Whether the laser is currently enabled.", stream="slow")
    def is_enabled(self) -> bool:
        """Check if the laser is enabled."""

    @property
    @abstractmethod
    @prop(label="Power", units="mW", desc="Measured laser output power.", stream="fast")
    def power(self) -> float:
        """Get the measured laser output power."""

    @number()
    @abstractmethod
    @prop(label="Power Setpoint", units="mW", desc="Commanded laser power.", stream="fast")
    def power_setpoint(self) -> float:
        """Get the commanded laser power setpoint."""

    @power_setpoint.setter
    @abstractmethod
    def power_setpoint(self, value: float) -> None:
        """Command the laser to a new power setpoint."""

    @property
    @abstractmethod
    @prop(label="Temperature", units="°C", desc="The temperature of the laser.")
    def temperature_c(self) -> float | None:
        """Get the temperature of the laser in degrees Celsius."""
