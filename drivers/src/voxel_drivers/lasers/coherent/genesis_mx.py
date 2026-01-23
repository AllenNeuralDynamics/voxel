"""Coherent Genesis MX laser driver."""

from coherent_lasers.genesis_mx.commands import OperationModes
from coherent_lasers.genesis_mx.driver import GenesisMX as GenesisMXDriver
from pyrig.device.props import deliminated_float

from voxel.laser.base import Laser


class GenesisMX(Laser):
    """Coherent Genesis MX laser driver.

    Uses the coherent_lasers package for communication.
    """

    def __init__(self, uid: str, serial: str, wavelength: int, max_power_mw: float = 1000) -> None:
        """Initialize the Genesis MX laser.

        Args:
            uid: Unique identifier for this device.
            serial: Serial number of the laser.
            wavelength: Wavelength of the laser in nm.
            max_power_mw: Maximum power of the laser in mW. default is 1000 mW
        """
        self._serial = serial
        self._max_power_mw = max_power_mw

        try:
            self._inst = GenesisMXDriver(serial=serial)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Genesis MX laser {serial}: {e}") from e

        if self._inst.head.serial != serial:
            raise ValueError(f"Serial number mismatch: expected {serial}, got {self._inst.head.serial}")

        try:
            self._inst.mode = OperationModes.PHOTO
        except Exception as e:
            raise RuntimeError(f"Failed to set Genesis MX laser mode: {e}") from e

        super().__init__(uid=uid, wavelength=wavelength)

        self.enable()
        self.log.info(f"Initialized Genesis MX laser: serial={serial}, wavelength={wavelength}nm")

    def enable(self) -> None:
        """Enable the laser."""
        if self._inst is None:
            self._inst = GenesisMXDriver(serial=self._serial)
        self._inst.enable()
        self.log.debug("Laser enabled")

    def disable(self) -> None:
        """Disable the laser."""
        self._inst.disable()
        self.log.debug("Laser disabled")

    @property
    def is_enabled(self) -> bool:
        """Check if the laser is enabled."""
        return self._inst.enable_loop.software

    @deliminated_float(min_value=0.0, max_value=lambda self: self._max_power_mw, step=0.1)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in mW."""
        return self._inst.power_setpoint_mw

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in mW."""
        self._inst.power_mw = value
        self.log.debug(f"Power setpoint set to {value} mW")

    @property
    def power_mw(self) -> float:
        """Get the actual power of the laser in mW."""
        return self._inst.power_mw

    @property
    def temperature_c(self) -> float:
        """Get the temperature of the laser in degrees Celsius."""
        return self._inst.temperature_c

    def close(self) -> None:
        """Close the laser connection."""
        self.log.info("Closing Genesis MX laser")
        self.disable()
