"""Vortran Stradus laser over serial; the laser takes power values only while it emits."""

from enum import IntFlag
from math import isfinite
from time import monotonic, sleep
from typing import ClassVar

from rigup.device import fact, query, stream
from serial import Serial, SerialException
from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.light import ControlMode, Laser
from vxl_drivers.serial import SerialTransport

_EOL = b"\r\n"
_MAX_BLANK_LINES = 4
_SETUP_QUIET_S = 0.2
_WAVELENGTH_MATCH_NM = 5.0
_EMISSION_TIMEOUT_S = 10.0
_POLL_S = 0.2


class StradusError(ConnectionError):
    """A refused command, missing reply, or failed readback."""


class Status(IntFlag):
    """Bits of the ?FC reply; zero means emission is active with no fault."""

    STANDBY = 1
    WARMUP = 2
    VALUE_OUT_OF_RANGE = 4
    INVALID_COMMAND = 8
    INTERLOCK_OPEN = 16
    TEC_OFF = 32
    DIODE_OVER_CURRENT = 64
    DIODE_TEMPERATURE_FAULT = 128
    BASE_PLATE_TEMPERATURE_FAULT = 256
    BUFFER_OVERFLOW = 512
    EEPROM_ERROR = 1024
    I2C_ERROR = 2048
    COMMAND_TIMEOUT = 4096
    WATCHDOG_ERROR = 8192
    FATAL_ERROR = 16384
    DIODE_END_OF_LIFE = 32768


_STARTING = Status.STANDBY | Status.WARMUP
_BLOCKING = Status(0x7FF0)


class StradusLaser(Laser):
    """One Stradus per serial port, with its power in mW.

    The laser ignores power values while off, so :meth:`on` writes the saved value once emission starts, and waits
    out the startup delay. :meth:`off` parks the power at 0 first, so emission never starts above the saved value.
    The laser changes its control mode only while it is off, so a change while it is on turns it off, changes the
    mode, and turns it on again. It does not do mixed control."""

    unit: ClassVar[str] = "mW"

    def __init__(
        self,
        uid: str,
        port: str,
        wavelength: float,
        *,
        startup_delay_s: float = 0.0,
        setpoint_tolerance_mw: float = 1.0,
        baud: int = 19200,
        timeout_s: float = 1.0,
    ) -> None:
        super().__init__(uid=uid)
        if isinstance(wavelength, bool) or not isfinite(wavelength) or wavelength <= 0:
            raise ValueError("wavelength must be finite and positive in nm")
        if not isfinite(startup_delay_s) or startup_delay_s < 0:
            raise ValueError("startup delay must be finite and nonnegative")
        if not isfinite(setpoint_tolerance_mw) or setpoint_tolerance_mw <= 0:
            raise ValueError("setpoint tolerance must be finite and positive")
        if baud <= 0 or not isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("baud and timeout must be positive")
        self._wavelength = float(wavelength)
        self._startup_delay_s = startup_delay_s
        self._setpoint_tolerance_mw = setpoint_tolerance_mw
        self._max_power_mw = 0.0
        self._setpoint_mw = 0.0
        self._enabled_at: float | None = None
        self._closed = False
        self._t = SerialTransport(port, baud=baud, timeout=timeout_s)
        try:
            self._t.ser.write_timeout = timeout_s
            self._initialize()
        except Exception as error:
            try:
                self.off()
            except Exception as cleanup_error:
                raise ExceptionGroup("Stradus initialization and inhibition failed", [error, cleanup_error]) from None
            finally:
                self._t.close()
            raise
        self.log.info(f"Initialized Stradus: {self._identification}, max_power={self._max_power_mw} mW")

    def _initialize(self) -> None:
        with self._t.transaction() as port:
            self._t.drain_input()
            # Replies to these setup commands depend on the current echo and prompt state, so discard them.
            # TODO: verify on real hardware that ECHO=0 and PROMPT=0 need no other reply handling.
            for setup in ("ECHO=0", "PROMPT=0"):
                port.write(f"{setup}\r".encode("ascii"))
                self._t.drain_input(quiet_s=_SETUP_QUIET_S)
            reported = self._number("LW")
            if abs(reported - self._wavelength) > _WAVELENGTH_MATCH_NM:
                raise ValueError(f"Stradus reports {reported} nm, but {self._wavelength} nm is configured")
            self._identification = self._query("LI")
            self._firmware_version = self._query("FV")
            self._max_power_mw = self._number("MAXP")
            if self._max_power_mw <= 0:
                raise StradusError(f"Invalid Stradus maximum power {self._max_power_mw} mW")
            # Adopt the stored target before disable parks the hardware at 0.
            self._setpoint_mw = min(max(self._number("LPS"), 0.0), self._max_power_mw)
            self.off()
            self._write_control_mode("software")

    def _exchange(self, name: str, value: object = None) -> str:
        """Send ?NAME or NAME=value and return the value from the NAME=value reply."""
        message = f"?{name}" if value is None else f"{name}={value}"
        with self._t.transaction() as port:
            self._t.drain_input()
            try:
                port.write(f"{message}\r".encode("ascii"))
                line = _read_line(port)
            except SerialException as error:
                raise StradusError(f"Serial error for {message!r}: {error}") from error
        reply_name, separator, reply_value = line.partition("=")
        if not separator or reply_name.strip().lstrip("?").upper() != name.upper():
            raise StradusError(f"Unexpected reply to {message!r}: {line!r}")
        return reply_value.strip()

    def _query(self, name: str) -> str:
        return self._exchange(name)

    def _number(self, name: str) -> float:
        reply = self._query(name)
        try:
            value = float(reply)
        except ValueError as error:
            raise StradusError(f"Expected a number for ?{name}, got {reply!r}") from error
        if not isfinite(value):
            raise StradusError(f"Stradus returned a nonfinite number for ?{name}")
        return value

    def _flag(self, name: str) -> bool:
        reply = self._query(name)
        if reply not in ("0", "1"):
            raise StradusError(f"Expected 0 or 1 for ?{name}, got {reply!r}")
        return reply == "1"

    def _switch(self, name: str, on: bool) -> None:
        """Set a 0/1 command; the reply is the resulting state, 0 when the laser refuses."""
        if self._exchange(name, int(on)) != str(int(on)):
            raise StradusError(f"Stradus refused {name}={int(on)}; status: {self._status_names()}")

    def _status(self) -> Status:
        """Read ?FC; the laser reports a cleared fault once, then forgets it."""
        reply = self._query("FC")
        try:
            return Status(int(reply))
        except ValueError as error:
            raise StradusError(f"Expected a status code for ?FC, got {reply!r}") from error

    def _status_names(self) -> str:
        return ", ".join(flag.name or "" for flag in self._status()) or "emission active"

    @property
    def wavelength(self) -> float:
        return self._wavelength

    @property
    def power(self) -> float:
        self._ensure_open()
        return self._setpoint_mw

    @property
    def power_range(self) -> Span:
        return Span(0.0, self._max_power_mw)

    @property
    def is_on(self) -> bool:
        return not self._closed and self._flag("LE")

    @property
    def control_mode(self) -> ControlMode:
        self._ensure_open()
        with self._t.transaction():
            if self._flag("C"):
                raise StradusError("Stradus current control was set outside this driver")
            analog = self._flag("EPC")
            digital = self._flag("PUL")
        if analog and digital:
            raise StradusError("Stradus analog and digital modulation are both on")
        return "analog" if analog else "digital" if digital else "software"

    @property
    def pins(self) -> list[Pin]:
        return [
            Pin(name="ttl_in", direction="in", kind="digital"),
            Pin(name="analog_in", direction="in", kind="analog"),
        ]

    def on(self) -> None:
        self._ensure_open()
        with self._t.transaction():
            try:
                self._enable()
            except Exception as error:
                try:
                    self.off()
                except Exception as cleanup_error:
                    raise ExceptionGroup("Stradus enable and inhibition failed", [error, cleanup_error]) from None
                raise

    def _enable(self) -> None:
        if not self.is_on:
            self._switch("LE", True)
            self._enabled_at = monotonic()
            self._wait_for_emission()
            self._write_power(self._setpoint_mw, self.control_mode)
        if self._enabled_at is None:
            self._enabled_at = monotonic()
        remaining = self._startup_delay_s - (monotonic() - self._enabled_at)
        if remaining > 0:
            sleep(remaining)
        if not self.is_on:
            raise StradusError("Stradus emission permission was lost during startup")

    # TODO: verify on real hardware that ?FC drops STANDBY and WARMUP once emission is active.
    def _wait_for_emission(self) -> None:
        """Wait out the 5 s CDRH delay; stop early on a fault seen in two reads in a row."""
        deadline = monotonic() + _EMISSION_TIMEOUT_S
        previous = Status(0)
        while (status := self._status()) & (_STARTING | _BLOCKING):
            if status & previous & _BLOCKING or monotonic() > deadline:
                names = ", ".join(flag.name or "" for flag in status)
                raise StradusError(f"Stradus is not emitting: {names}")
            previous = status
            sleep(_POLL_S)

    def off(self) -> None:
        if self._closed:
            return
        with self._t.transaction():
            if self._flag("LE"):
                try:
                    self._park()
                except StradusError as error:
                    self.log.warning(f"Could not park Stradus power at 0; the next enable starts higher: {error}")
            self._switch("LE", False)
        self._enabled_at = None

    def _park(self) -> None:
        mode: ControlMode = "digital" if self._flag("PUL") else "software"
        name, readback_name = _power_names(mode)
        self._exchange(name, 0)
        if (parked := self._number(readback_name)) > self._setpoint_tolerance_mw:
            raise StradusError(f"power reads {parked} mW")

    def _set_power(self, value: float) -> None:
        """Write and confirm while emitting; otherwise save the value for the next :meth:`on`."""
        self._ensure_open()
        with self._t.transaction():
            if self.is_on:
                self._write_power(value, self.control_mode)
            self._setpoint_mw = value

    # TODO: verify on real hardware that ?LPS rounds to whole mW and ?PP returns the setting, not a measurement.
    def _write_power(self, value: float, mode: ControlMode) -> None:
        name, readback_name = _power_names(mode)
        self._exchange(name, f"{value:.1f}")
        readback = self._number(readback_name)
        if abs(readback - value) > self._setpoint_tolerance_mw:
            raise StradusError(f"Stradus power setpoint reads {readback} mW after setting {value} mW")

    @property
    @stream("fast", label="Measured Power", units="mW")
    def measured_power_mw(self) -> float:
        self._ensure_open()
        return self._number("LP")

    @property
    @stream("slow", label="Base Plate Temperature", units="°C")
    def temperature_c(self) -> float:
        self._ensure_open()
        return self._number("BPT")

    @property
    @fact(label="Identification")
    def identification(self) -> str:
        """Serial number, part number, nominal wavelength, nominal power, and beam shape."""
        return self._identification

    @property
    @fact(label="Firmware Version")
    def firmware_version(self) -> str:
        return self._firmware_version

    @property
    @stream("slow", label="Operating Hours", units="h")
    def operating_hours(self) -> float:
        self._ensure_open()
        return self._number("LH")

    @property
    @stream("slow", label="Diode Current", units="mA")
    def diode_current_ma(self) -> float:
        self._ensure_open()
        return self._number("LC")

    @property
    @stream("slow", label="Optical Block Temperature", units="°C")
    def optical_block_temperature_c(self) -> float:
        self._ensure_open()
        return self._number("OBT")

    @property
    @stream(label="Interlock Closed")
    def interlock_closed(self) -> bool:
        self._ensure_open()
        return self._flag("IL")

    @property
    @stream("slow", label="CDRH Delay")
    def cdrh_delay(self) -> bool:
        """Whether emission starts 5 s after enable."""
        self._ensure_open()
        return self._flag("DELAY")

    @query(label="Status")
    def status(self) -> list[str]:
        """Active states and faults, including faults cleared since the last read; empty means emitting."""
        self._ensure_open()
        return [flag.name or "" for flag in self._status()]

    def _set_control_mode(self, mode: ControlMode) -> None:
        self._ensure_open()
        if mode == "mixed":
            raise ValueError(f"{self.uid} does not do mixed control")
        with self._t.transaction():
            if self.control_mode == mode:
                return
            was_on = self.is_on
            if was_on:
                self.off()
            self._write_control_mode(mode)
            if was_on:
                self.on()

    # TODO: verify on real hardware that pulse mode works in power control (C=0), as the manual says;
    # the vortran_laser package claims it needs current control.
    def _write_control_mode(self, mode: ControlMode) -> None:
        with self._t.transaction():
            self._switch("C", False)
            states = {"EPC": mode == "analog", "PUL": mode == "digital"}
            for name, on in sorted(states.items(), key=lambda item: item[1]):
                self._switch(name, on)
            if self.control_mode != mode:
                raise StradusError(f"Stradus did not establish {mode} control")

    def dispose(self) -> None:
        """Turn the laser off, then release the serial port; failures can be retried."""
        if self._closed:
            return
        self.off()
        self._t.close()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Stradus laser is closed")


def _power_names(mode: ControlMode) -> tuple[str, str]:
    """Return the power command and its setpoint query; pulse mode uses peak power."""
    return ("PP", "PP") if mode == "digital" else ("LP", "LPS")


def _read_line(port: Serial) -> str:
    """Skip the blank line that starts each reply and return the first line with text."""
    for _ in range(_MAX_BLANK_LINES):
        raw = port.read_until(_EOL, size=4096)
        if not raw.endswith(_EOL):
            raise StradusError("Incomplete Stradus reply; check the port and baud")
        if line := raw.decode("ascii", errors="replace").strip():
            return line
    raise StradusError("Stradus sent only blank lines")
