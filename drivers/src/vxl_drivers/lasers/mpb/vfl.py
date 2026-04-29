"""MPB Communications VFL laser driver.

Targets the SHG variant by default. The wavelength constant is a placeholder —
verify against the unit's nameplate. The max-power bound is queried from the
firmware at init (`GETPOWERSETPTLIM 0`); the constant only serves as a fallback
if the query fails.

Adapted from the Lantz reference driver, with corrections cross-checked against
ZhuangLab/storm-control, python-microscopy/PYME, and ograsdijk/MPBC-VYFA-SF:
    - baud 9600 (Lantz had 1200, contradicted by all three independent sources)
    - dual prompt stripping ("D >" ready, "F >" fault)
    - runtime power-limit detection via GETPOWERSETPTLIM
    - error-string detection on responses

References:
    https://github.com/LabPy/lantz/blob/0.3/lantz/drivers/mpb/vfl.py
    https://github.com/ZhuangLab/storm-control
    https://github.com/python-microscopy/python-microscopy
    https://github.com/ograsdijk/MPBC-VYFA-SF
"""

import threading
from enum import StrEnum

from rigup.device.props import enumerated, numeric

from rigup import describe
from vxl.laser.base import Laser
from vxl_drivers.serial import SerialTransport

DEFAULT_BAUD = 9600
DEFAULT_WAVELENGTH_NM = 561
DEFAULT_MAX_POWER_MW = 500.0
DEFAULT_MAX_CURRENT_MA = 5000.0

_PROMPTS = ("D >", "F >")
_ERROR_MARKERS = ("MISSING_ARGUMENT", "DATA_CANNOT_BE_SET", "CAN_ONLY_BE_USED_FOR_TESTS")


class MpbCommandError(RuntimeError):
    """Raised when the MPB device reports a command error in its response."""


class Cmd(StrEnum):
    """Wire-format setters."""

    LD_ENABLE = "SETLDENABLE"
    POWER_ENABLE = "POWERENABLE"
    POWER_SETPOINT = "SETPOWER 0"
    CURRENT_SETPOINT = "SETLDCUR 1"
    SHG_TEMP_SETPOINT = "SETSHGTEMP"
    SHG_TUNE = "SETSHGCMD"


class Query(StrEnum):
    """Wire-format getters."""

    MODEL = "GETMODEL"
    LD_ENABLE = "GETLDENABLE"
    POWER_ENABLE = "GETPOWERENABLE"
    POWER_SETPOINT = "GETPOWER 0"
    POWER = "POWER 0"
    POWER_LIMITS = "GETPOWERSETPTLIM 0"
    CURRENT_SETPOINT = "GETLDCUR 1"
    LD_CURRENT = "LDCURRENT 1"
    LD_TEMP = "LDTEMP 1"
    TEC_TEMP = "TECTEMP 1"
    SHG_TEMP_SETPOINT = "GETSHGTEMP"
    SHG_TEMP = "SHGTEMP"
    SHG_TUNE_INFO = "GETSHGTUNERDY"
    SHG_TUNE_STATE = "GETSHGTUNESTATE"
    STATUS = "shlaser"


class ControlMode(StrEnum):
    """Laser control mode."""

    APC = "APC"  # Active Power Control (constant power)
    ACC = "ACC"  # Active Current Control (constant current)


_MODE_TO_WIRE = {ControlMode.APC: "1", ControlMode.ACC: "0"}
_WIRE_TO_MODE = {v: k for k, v in _MODE_TO_WIRE.items()}


class MpbVfl(Laser):
    """MPB Communications VFL laser driver (SHG variant).

    Single laser per serial port. Forced into APC mode at init; switch via
    `control_mode` if needed.
    """

    def __init__(
        self,
        uid: str,
        port: str,
        wavelength: int = DEFAULT_WAVELENGTH_NM,
        max_power_mw: float = DEFAULT_MAX_POWER_MW,
        max_current_ma: float = DEFAULT_MAX_CURRENT_MA,
        baud: int = DEFAULT_BAUD,
    ) -> None:
        """Initialize the MPB VFL laser.

        Args:
            uid: Unique identifier for this device.
            port: Serial port for communication.
            wavelength: Wavelength of the laser in nm.
            max_power_mw: Maximum optical output power in mW.
            max_current_ma: Maximum diode current in mA (for ACC mode).
            baud: Serial baud rate.
        """
        self._max_power_mw = max_power_mw
        self._max_current_ma = max_current_ma
        self._t = SerialTransport(port, baud=baud)
        self._lock = threading.Lock()

        super().__init__(uid=uid, wavelength=wavelength)

        self._idn = self._query(Query.MODEL)
        self._query(f"{Cmd.POWER_ENABLE} {_MODE_TO_WIRE[ControlMode.APC]}")
        self._max_power_mw = self._detect_max_power(fallback=max_power_mw)

        self.log.info(
            f"Initialized MPB VFL laser: port={port}, model={self._idn}, "
            f"wavelength={wavelength}nm, max_power={self._max_power_mw}mW",
        )

    def _detect_max_power(self, fallback: float) -> float:
        """Query firmware-reported power limits; fall back if the query fails.

        Reply format: ``"<min> <max>"`` in mW (per PYME's published usage).
        """
        try:
            reply = self._query(Query.POWER_LIMITS)
            parts = reply.split()
            if len(parts) >= 2:
                detected = float(parts[1])
                if detected > 0:
                    return detected
        except (ValueError, MpbCommandError) as e:
            self.log.warning(f"Could not detect power limits ({e!r}); using fallback {fallback} mW")
        return fallback

    def _query(self, msg: str) -> str:
        """Send a command and return the trimmed response.

        Strips the trailing reply terminator and either the ready (``D >``) or
        fault (``F >``) prompt. Raises :class:`MpbCommandError` if the device
        responds with a recognized error marker.
        """
        with self._lock:
            self._t.ser.reset_input_buffer()
            self._t.write(f"{msg}\r".encode("ascii"))
            line = self._t.readline() or b""

        text = line.decode("ascii", errors="replace").strip()
        for prompt in _PROMPTS:
            text = text.removesuffix(prompt).strip()
        for marker in _ERROR_MARKERS:
            if marker in text:
                raise MpbCommandError(f"Device rejected command {msg!r}: {text}")
        return text

    def enable(self) -> None:
        """Enable laser emission."""
        self._query(f"{Cmd.LD_ENABLE} 1")
        self.log.debug("Laser enabled")

    def disable(self) -> None:
        """Disable laser emission."""
        self._query(f"{Cmd.LD_ENABLE} 0")
        self.log.debug("Laser disabled")

    @property
    def is_enabled(self) -> bool:
        """Check if the laser diode is enabled."""
        return self._query(Query.LD_ENABLE) == "1"

    @numeric(minimum=0.0, maximum=lambda self: self._max_power_mw, step=1.0)
    @describe(label="Power Setpoint", units="mW", desc="Commanded laser power (APC mode).", stream=True)
    def power_setpoint(self) -> float:
        """Get the commanded power setpoint in mW."""
        return float(self._query(Query.POWER_SETPOINT))

    @power_setpoint.setter
    def power_setpoint(self, value: float) -> None:
        """Set the commanded power setpoint in mW."""
        self._query(f"{Cmd.POWER_SETPOINT} {value:.0f}")
        self.log.debug(f"Power setpoint set to {value} mW")

    @property
    @describe(label="Power", units="mW", desc="Measured laser output power.", stream=True)
    def power(self) -> float:
        """Get the measured output power in mW."""
        return float(self._query(Query.POWER))

    @numeric(minimum=0.0, maximum=lambda self: self._max_current_ma, step=1.0)
    @describe(label="Current Setpoint", units="mA", desc="Commanded diode current (ACC mode).", stream=True)
    def current_setpoint_ma(self) -> float:
        """Get the commanded diode current setpoint in mA."""
        return float(self._query(Query.CURRENT_SETPOINT))

    @current_setpoint_ma.setter
    def current_setpoint_ma(self, value: float) -> None:
        """Set the commanded diode current setpoint in mA."""
        self._query(f"{Cmd.CURRENT_SETPOINT} {value:.1f}")
        self.log.debug(f"Current setpoint set to {value} mA")

    @property
    @describe(label="Diode Current", units="mA", desc="Measured laser diode current.", stream=True)
    def ld_current_ma(self) -> float:
        """Get the measured laser diode current in mA."""
        return float(self._query(Query.LD_CURRENT))

    @property
    @describe(label="Temperature", units="°C", desc="Laser diode temperature.", stream=True)
    def temperature_c(self) -> float | None:
        """Get the laser diode temperature in °C."""
        return float(self._query(Query.LD_TEMP))

    @property
    @describe(label="TEC Temperature", units="°C", desc="Thermoelectric cooler temperature.", stream=True)
    def tec_temp_c(self) -> float:
        """Get the TEC temperature in °C."""
        return float(self._query(Query.TEC_TEMP))

    @enumerated(options=list(ControlMode))
    @describe(label="Control Mode", desc="APC (constant power) or ACC (constant current).")
    def control_mode(self) -> str:
        """Get the active control mode."""
        wire = self._query(Query.POWER_ENABLE)
        return _WIRE_TO_MODE.get(wire, ControlMode.APC).value

    @control_mode.setter
    def control_mode(self, value: str) -> None:
        """Set the active control mode."""
        mode = ControlMode(value)
        self._query(f"{Cmd.POWER_ENABLE} {_MODE_TO_WIRE[mode]}")
        self.log.debug(f"Control mode set to {value}")

    @property
    @describe(label="Model", desc="Identification string reported by the device.")
    def idn(self) -> str:
        """Get the device identification string."""
        return self._idn

    @numeric(minimum=0.0, maximum=200.0, step=0.01)
    @describe(label="SHG Temp Setpoint", units="°C", desc="Commanded SHG crystal temperature.", stream=True)
    def shg_temp_setpoint_c(self) -> float:
        """Get the SHG temperature setpoint in °C."""
        return float(self._query(Query.SHG_TEMP_SETPOINT))

    @shg_temp_setpoint_c.setter
    def shg_temp_setpoint_c(self, value: float) -> None:
        """Set the SHG temperature setpoint in °C."""
        self._query(f"{Cmd.SHG_TEMP_SETPOINT} {value:.2f}")
        self.log.debug(f"SHG temp setpoint set to {value} °C")

    @property
    @describe(label="SHG Temperature", units="°C", desc="Measured SHG crystal temperature.", stream=True)
    def shg_temp_c(self) -> float:
        """Get the measured SHG crystal temperature in °C."""
        return float(self._query(Query.SHG_TEMP))

    @describe(label="SHG Tune Info", desc="Whether the laser is ready for SHG tuning.")
    def shg_tune_info(self) -> str:
        """Get a description of the SHG tuning readiness."""
        info = self._query(Query.SHG_TUNE_INFO).split()
        if len(info) < 3:
            return "Unknown SHG tune state."
        ready = "Laser ready for SHG tuning. " if info[0] == "1" else "Laser not ready for SHG tuning. "
        schedule = f"Next SHG tuning scheduled in {info[1]} hours of operation. "
        warm = f"Warm-up period expires in {info[2]} seconds."
        return ready + schedule + warm

    @describe(label="Tune SHG", desc="Initiate SHG tuning.")
    def tune_shg(self) -> None:
        """Initiate SHG tuning."""
        self._query(f"{Cmd.SHG_TUNE} 1")
        self.log.debug("SHG tuning initiated")

    @describe(label="Stop SHG Tuning", desc="Abort SHG tuning.")
    def tune_shg_stop(self) -> None:
        """Abort SHG tuning."""
        self._query(f"{Cmd.SHG_TUNE} 2")
        self.log.debug("SHG tuning aborted")

    @describe(label="Status", desc="Multi-line status report from `shlaser`.")
    def status(self) -> list[str]:
        """Get the status report as a list of lines."""
        return self._query(Query.STATUS).split("\r")

    def close(self) -> None:
        """Close the laser connection."""
        self.log.info("Closing MPB VFL laser")
        try:
            self.disable()
        except Exception as e:
            self.log.warning(f"Error disabling laser on close: {e}")
        self._t.close()
