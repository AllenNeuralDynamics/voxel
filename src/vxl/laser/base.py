from abc import abstractmethod

from rigup import Device, deliminated_float, describe, numeric
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

    @numeric()
    @abstractmethod
    @describe(label="Power", units="mW", desc="Measured power; writes command the setpoint.", stream=True)
    def power(self) -> float:
        """Get the measured power. Writes command the setpoint (target tracks it)."""

    @power.setter
    @abstractmethod
    def power(self, value: float) -> None:
        """Command the laser to a new power setpoint."""

    # ── Deprecated: superseded by ``power`` (which carries both measured value and setpoint target). ──
    # Kept for backward compatibility during the migration window. Will be removed in Phase 2.

    @deliminated_float()
    @abstractmethod
    @describe(label="Power Setpoint", units="mW", desc="The target power setpoint.", stream=True)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in mW. (Deprecated — use ``power.target``.)"""

    @power_setpoint_mw.setter
    @abstractmethod
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in mW. (Deprecated — assign to ``power``.)"""

    @property
    @abstractmethod
    @describe(label="Power (legacy)", units="mW", desc="The actual power of the laser.", stream=True)
    def power_mw(self) -> float:
        """Get the actual power of the laser in mW. (Deprecated — use ``power``.)"""

    @property
    @abstractmethod
    @describe(label="Temperature", units="°C", desc="The temperature of the laser.")
    def temperature_c(self) -> float | None:
        """Get the temperature of the laser in degrees Celsius."""
