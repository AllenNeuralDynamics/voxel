"""Cobolt Skyra laser driver."""

from enum import StrEnum

from pycobolt import CoboltLaser
from pyrig.device.props import deliminated_float, enumerated_string
from voxel.laser.base import Laser

from pyrig import describe


class Cmd(StrEnum):
    """Command strings for controlling the Skyra laser."""

    LASER_ENABLE = "l1"
    LASER_DISABLE = "l0"
    ENABLE_MODULATION = "em"
    CONSTANT_POWER_MODE = "cp"
    ENABLE_DIGITAL_MODULATION = "sdmes 1"
    DISABLE_DIGITAL_MODULATION = "sdmes 0"
    ENABLE_ANALOG_MODULATION = "sames 1"
    DISABLE_ANALOG_MODULATION = "sames 0"
    POWER_SETPOINT = "p"
    CURRENT_SETPOINT = "slc"


class Query(StrEnum):
    """Query strings for retrieving Skyra laser status."""

    MODULATION_MODE = "gmes?"
    ANALOG_MODULATION_MODE = "games?"
    DIGITAL_MODULATION_MODE = "gdmes?"
    POWER_SETPOINT = "p?"


class ModulationMode(StrEnum):
    """Modulation modes for Cobolt Skyra laser."""

    OFF = "off"
    ANALOG = "analog"
    DIGITAL = "digital"


# Modulation mode command mappings
_MODULATION_CMDS = {
    "off": {
        "external_control": Cmd.CONSTANT_POWER_MODE,
        "digital": Cmd.DISABLE_DIGITAL_MODULATION,
        "analog": Cmd.DISABLE_ANALOG_MODULATION,
    },
    "analog": {
        "external_control": Cmd.ENABLE_MODULATION,
        "digital": Cmd.DISABLE_DIGITAL_MODULATION,
        "analog": Cmd.ENABLE_ANALOG_MODULATION,
    },
    "digital": {
        "external_control": Cmd.ENABLE_MODULATION,
        "digital": Cmd.ENABLE_DIGITAL_MODULATION,
        "analog": Cmd.DISABLE_ANALOG_MODULATION,
    },
}


class CoboltSkyra(Laser):
    """Cobolt Skyra multi-line laser driver.

    Uses the pycobolt package for communication.
    """

    def __init__(
        self,
        uid: str,
        wavelength: int,
        port: str,
        prefix: str,
        max_power_mw: float,
        min_current_ma: float = 0.0,
        max_current_ma: float = 100.0,
    ) -> None:
        """Initialize the Cobolt Skyra laser.

        Args:
            uid: Unique identifier for this device.
            wavelength: Wavelength of the laser line in nm.
            port: Serial port for communication.
            prefix: Command prefix for the laser line.
            max_power_mw: Maximum power in mW.
            min_current_ma: Minimum current in mA.
            max_current_ma: Maximum current in mA.
        """
        self._inst = CoboltLaser(port)
        self._prefix = prefix
        self._max_power_mw = max_power_mw
        self._min_current_ma = min_current_ma
        self._max_current_ma = max_current_ma
        self._current_setpoint_ma = min_current_ma

        super().__init__(uid=uid, wavelength=wavelength)
        self.log.info(f"Initialized Cobolt Skyra laser: port={port}, prefix={prefix}, wavelength={wavelength}nm")

    def enable(self) -> None:
        """Enable the laser."""
        self._inst.send_cmd(f"{self._prefix}{Cmd.LASER_ENABLE}")
        self.log.debug(f"Laser {self._prefix} enabled")

    def disable(self) -> None:
        """Disable the laser."""
        self._inst.send_cmd(f"{self._prefix}{Cmd.LASER_DISABLE}")
        self.log.debug(f"Laser {self._prefix} disabled")

    @property
    def is_enabled(self) -> bool:
        """Check if the laser is enabled."""
        return self._inst.is_on()

    @property
    def max_power_mw(self) -> float:
        """Get the maximum power in mW."""
        return self._max_power_mw

    @deliminated_float(min_value=0.0, max_value=lambda self: self._max_power_mw, step=0.1)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in mW."""
        if self._is_constant_current():
            # In constant current mode, we track the setpoint internally
            return self._current_setpoint_ma  # This is a simplification
        response = self._inst.send_cmd(f"{self._prefix}{Query.POWER_SETPOINT}")
        return float(response) * 1000  # Convert W to mW

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in mW."""
        if self.modulation_mode != "off":
            # In modulation mode, set current directly
            # This is simplified - the classic driver uses polynomial conversion
            self._current_setpoint_ma = value  # Store for getter
            self._inst.send_cmd(f"{self._prefix}{Cmd.CURRENT_SETPOINT} {value}")
        else:
            # In constant power mode, set power in Watts
            power_w = value / 1000.0
            self._inst.send_cmd(f"{self._prefix}{Cmd.POWER_SETPOINT} {power_w}")
        self.log.debug(f"Power setpoint set to {value} mW")

    @property
    def power_mw(self) -> float:
        """Get the actual power of the laser in mW."""
        return self._inst.get_power()

    @property
    def temperature_c(self) -> float | None:
        """Get the temperature of the laser in degrees Celsius."""
        # Skyra doesn't expose temperature via serial
        return None

    @enumerated_string(options=list(ModulationMode))
    @describe(label="Modulation Mode", desc="Laser modulation mode.")
    def modulation_mode(self) -> str:
        """Get the modulation mode."""
        result = self._inst.send_cmd(f"{self._prefix}{Query.MODULATION_MODE}")
        if result == "0":
            return "off"

        analog_result = self._inst.send_cmd(f"{self._prefix}{Query.ANALOG_MODULATION_MODE}")
        if analog_result == "1":
            return "analog"

        return "digital"

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        """Set the modulation mode."""
        if value not in _MODULATION_CMDS:
            raise ValueError(f"Invalid modulation mode: {value}")

        cmds = _MODULATION_CMDS[value]
        self._inst.send_cmd(f"{self._prefix}{cmds['external_control']}")
        self._inst.send_cmd(f"{self._prefix}{cmds['digital']}")
        self._inst.send_cmd(f"{self._prefix}{cmds['analog']}")
        self.log.debug(f"Modulation mode set to {value}")

    def _is_constant_current(self) -> bool:
        """Check if in constant current mode."""
        # get_mode() returns "0" for constant current, "1" for constant power, "2" for modulation
        mode = self._inst.get_mode()
        return mode == "0" or "Constant Current" in mode

    def close(self) -> None:
        """Close the laser connection."""
        self.log.info("Closing Cobolt Skyra laser")
        self.disable()
        if self._inst.is_connected():
            self._inst.disconnect()
