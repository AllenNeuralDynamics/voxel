from abc import abstractmethod

from pyrig import Device, describe
from pyrig.device.props import deliminated_float
from spim_rig.device import DeviceType


class SpimLaser(Device):
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

    @deliminated_float()
    @abstractmethod
    @describe(label="Power Setpoint", units="mW", desc="The target power setpoint.", stream=True)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in mW."""

    @power_setpoint_mw.setter
    @abstractmethod
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in mW."""

    @property
    @abstractmethod
    @describe(label="Power", units="mW", desc="The actual power of the laser.", stream=True)
    def power_mw(self) -> float:
        """Get the actual power of the laser in mW."""

    @property
    @abstractmethod
    @describe(label="Temperature", units="°C", desc="The temperature of the laser.")
    def temperature_c(self) -> float | None:
        """Get the temperature of the laser in degrees Celsius."""
