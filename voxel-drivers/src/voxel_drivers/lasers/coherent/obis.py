"""Coherent OBIS laser drivers (LX and LS variants)."""

from enum import StrEnum

from obis_laser import LSModulationType, LXModulationType
from obis_laser import ObisLS as ObisLSDriver
from obis_laser import ObisLX as ObisLXDriver
from pyrig.device.props import deliminated_float, enumerated_string
from serial import Serial
from voxel.laser.base import Laser

from pyrig import describe


class ModulationMode(StrEnum):
    """Modulation modes for OBIS lasers."""

    OFF = "off"
    ANALOG = "analog"
    DIGITAL = "digital"
    MIXED = "mixed"


# Mapping from our ModulationMode to OBIS LS modulation types
_LS_MODULATION_MAP: dict[str, str] = {
    "off": LSModulationType.CW_POWER,
    "analog": LSModulationType.ANALOG,
    "digital": LSModulationType.DIGITAL,
    "mixed": LSModulationType.MIXED,
}

# Mapping from our ModulationMode to OBIS LX modulation types
_LX_MODULATION_MAP: dict[str, str] = {
    "off": LXModulationType.CW_POWER,
    "analog": LXModulationType.ANALOG,
    "digital": LXModulationType.DIGITAL,
    "mixed": LXModulationType.MIXED,
}


class ObisLX(Laser):
    """Coherent OBIS LX laser driver.

    Uses the obis_laser package for communication.
    """

    def __init__(
        self,
        uid: str,
        wavelength: int,
        port: Serial | str,
        prefix: str | None = None,
    ) -> None:
        """Initialize the OBIS LX laser.

        Args:
            uid: Unique identifier for this device.
            wavelength: Wavelength of the laser in nm.
            port: Serial port for communication.
            prefix: Command prefix for the laser (for multi-laser setups).
        """
        self._prefix = prefix
        self._inst = ObisLXDriver(port, self._prefix)

        super().__init__(uid=uid, wavelength=wavelength)
        self.log.info(f"Initialized OBIS LX laser: port={port}, wavelength={wavelength}nm")

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
        # OBIS doesn't have a direct enabled query - infer from power
        return self._inst.power_setpoint > 0

    @deliminated_float(min_value=0.0, max_value=lambda self: self._inst.max_power, step=0.1)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in mW."""
        return self._inst.power_setpoint

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in mW."""
        self._inst.power_setpoint = value
        self.log.debug(f"Power setpoint set to {value} mW")

    @property
    def power_mw(self) -> float:
        """Get the actual power of the laser in mW."""
        return self._inst.power_setpoint

    @property
    def temperature_c(self) -> float:
        """Get the temperature of the laser in degrees Celsius."""
        return self._inst.temperature

    @enumerated_string(options=list(ModulationMode))
    @describe(label="Modulation Mode", desc="Laser modulation mode.")
    def modulation_mode(self) -> str:
        """Get the modulation mode."""
        mode = self._inst.modulation_mode
        for key, value in _LX_MODULATION_MAP.items():
            if mode == str(value):
                return key
        self.log.warning(f"Unknown modulation mode: {mode}")
        return "off"

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        """Set the modulation mode."""
        if value not in _LX_MODULATION_MAP:
            raise ValueError(f"Invalid modulation mode: {value}. Must be one of {list(_LX_MODULATION_MAP.keys())}")
        self._inst.modulation_mode = _LX_MODULATION_MAP[value]  # pyright: ignore[reportAttributeAccessIssue]
        self.log.debug(f"Modulation mode set to {value}")

    @describe(label="Status", desc="Get laser system status.")
    def status(self) -> dict[str, str | float]:
        """Get the status of the laser."""
        return self._inst.get_system_status()

    def close(self) -> None:
        """Close the laser connection."""
        self.log.info("Closing OBIS LX laser")
        self._inst.disable()


class ObisLS(Laser):
    """Coherent OBIS LS laser driver.

    Uses the obis_laser package for communication. Very similar to LX
    but uses the ObisLS driver class.
    """

    def __init__(
        self,
        uid: str,
        wavelength: int,
        port: Serial | str,
        prefix: str | None = None,
    ) -> None:
        """Initialize the OBIS LS laser.

        Args:
            uid: Unique identifier for this device.
            wavelength: Wavelength of the laser in nm.
            port: Serial port for communication.
            prefix: Command prefix for the laser (for multi-laser setups).
        """
        self._prefix = prefix
        self._inst = ObisLSDriver(port, self._prefix)

        super().__init__(uid=uid, wavelength=wavelength)
        self.log.info(f"Initialized OBIS LS laser: port={port}, wavelength={wavelength}nm")

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
        return self._inst.power_setpoint > 0

    @deliminated_float(min_value=0.0, max_value=lambda self: self._inst.max_power, step=0.1)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in mW."""
        return self._inst.power_setpoint

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in mW."""
        self._inst.power_setpoint = value
        self.log.debug(f"Power setpoint set to {value} mW")

    @property
    def power_mw(self) -> float:
        """Get the actual power of the laser in mW."""
        return self._inst.power_setpoint

    @property
    def temperature_c(self) -> float:
        """Get the temperature of the laser in degrees Celsius."""
        return self._inst.temperature

    @enumerated_string(options=list(ModulationMode))
    @describe(label="Modulation Mode", desc="Laser modulation mode.")
    def modulation_mode(self) -> str:
        """Get the modulation mode."""
        mode = self._inst.modulation_mode
        for key, value in _LS_MODULATION_MAP.items():
            if mode == str(value):
                return key
        self.log.warning(f"Unknown modulation mode: {mode}")
        return "off"

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        """Set the modulation mode."""
        if value not in _LS_MODULATION_MAP:
            raise ValueError(f"Invalid modulation mode: {value}. Must be one of {list(_LS_MODULATION_MAP.keys())}")
        self._inst.modulation_mode = _LS_MODULATION_MAP[value]  # pyright: ignore[reportAttributeAccessIssue]
        self.log.debug(f"Modulation mode set to {value}")

    @describe(label="Status", desc="Get laser system status.")
    def status(self) -> dict[str, str | float]:
        """Get the status of the laser."""
        return self._inst.get_system_status()

    def close(self) -> None:
        """Close the laser connection."""
        self.log.info("Closing OBIS LS laser")
        self._inst.disable()
