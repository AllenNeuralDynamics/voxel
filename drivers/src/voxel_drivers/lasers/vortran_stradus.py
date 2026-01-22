"""Vortran Stradus laser driver."""

from enum import StrEnum

from pyrig.device.props import deliminated_float, enumerated_string
from vortran_laser import BoolVal
from vortran_laser import StradusLaser as StradusDriver
from voxel.laser.base import Laser

from pyrig import describe


class ModulationMode(StrEnum):
    """Modulation modes for Vortran Stradus laser."""

    OFF = "off"
    ANALOG = "analog"
    DIGITAL = "digital"


# Modulation mode to driver attribute mapping
_MODULATION_MAP = {
    "off": {"external_control": BoolVal.OFF, "digital_modulation": BoolVal.OFF},
    "analog": {"external_control": BoolVal.ON, "digital_modulation": BoolVal.OFF},
    "digital": {"external_control": BoolVal.OFF, "digital_modulation": BoolVal.ON},
}


class VortranStradus(Laser):
    """Vortran Stradus laser driver.

    Uses the vortran_laser package for communication.
    """

    def __init__(
        self,
        uid: str,
        wavelength: int,
        port: str,
    ) -> None:
        """Initialize the Vortran Stradus laser.

        Args:
            uid: Unique identifier for this device.
            wavelength: Wavelength of the laser in nm.
            port: Serial port for communication.
        """
        self._inst = StradusDriver(port)

        super().__init__(uid=uid, wavelength=wavelength)
        self.log.info(f"Initialized Vortran Stradus laser: port={port}, wavelength={wavelength}nm")

    def enable(self) -> None:
        """Enable the laser."""
        self._inst.enable()
        self.log.debug("Laser enabled")

    def disable(self) -> None:
        """Disable the laser."""
        self._inst.disable()
        self.log.debug("Laser disabled")

    @property
    def is_enabled(self) -> bool:
        """Check if the laser is enabled."""
        return self._inst.laser_is_emitting

    @deliminated_float(min_value=0.0, max_value=lambda self: float(self._inst.max_power), step=0.1)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in mW."""
        return float(self._inst.power_setpoint)

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in mW."""
        self._inst.power_setpoint = value
        self.log.debug(f"Power setpoint set to {value} mW")

    @property
    def power_mw(self) -> float:
        """Get the actual power of the laser in mW."""
        return float(self._inst.power)

    @property
    def temperature_c(self) -> float:
        """Get the temperature of the laser in degrees Celsius."""
        return float(self._inst.temperature)

    @enumerated_string(options=list(ModulationMode))
    @describe(label="Modulation Mode", desc="Laser modulation mode.")
    def modulation_mode(self) -> str:
        """Get the modulation mode."""
        # external_control returns raw string, digital_modulation returns BoolVal
        if BoolVal(self._inst.external_control) == BoolVal.ON:
            return "analog"
        if self._inst.digital_modulation == BoolVal.ON:
            return "digital"
        return "off"

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        """Set the modulation mode."""
        if value not in _MODULATION_MAP:
            raise ValueError(f"Invalid modulation mode: {value}")

        for attr, state in _MODULATION_MAP[value].items():
            setattr(self._inst, attr, state)
        self.log.debug(f"Modulation mode set to {value}")

    @describe(label="Status", desc="Get laser fault status.")
    def status(self) -> list[str] | None:
        """Get the status of the laser."""
        return self._inst.faults

    def close(self) -> None:
        """Close the laser connection."""
        self.log.info("Closing Vortran Stradus laser")
        self._inst.ser.close()
