"""Direct serial control of an AA Opto-Electronic MPDSnC controller."""

import re
from collections.abc import Generator
from contextlib import contextmanager
from enum import StrEnum
from math import isfinite
from time import sleep

from pydantic import BaseModel, ConfigDict
from serial import SerialException

from rigup import Device, describe, enumerated, numeric_int
from vxl_drivers.serial import SerialTransport

_EOL = b"\n\r"
_MAX_REPLY_BYTES = 65536
_LINE = re.compile(
    r"l(?P<line>\d+)\s+F=(?P<frequency>\d+\.\d+)\s+P=(?P<power>\d+\.\d+)"
    r"\s+(?P<state>ON|OFF)\s+(?P<mode>INTERNAL|EXTERNAL)",
    re.IGNORECASE,
)
_BLANKING = re.compile(r"Blanking\s+(ON|OFF)\s+(INTERNAL|EXTERNAL)", re.IGNORECASE)


class InputMode(StrEnum):
    """Whether a modulation input is controlled internally or externally."""

    INTERNAL = "internal"
    EXTERNAL = "external"


class MPDSCommunicationError(ConnectionError):
    """An incomplete, malformed, or unsuccessful controller transaction."""


class LineState(BaseModel):
    """RF settings reported by the controller, not measured optical output."""

    model_config = ConfigDict(frozen=True)
    frequency_mhz: float
    power_dbm: float
    enabled: bool
    input_mode: InputMode


class BlankingState(BaseModel):
    """Vendor blanking ON/OFF state and its independent input mode."""

    model_config = ConfigDict(frozen=True)
    enabled: bool
    input_mode: InputMode


class ControllerState(BaseModel):
    """One complete status response, including shared blanking."""

    model_config = ConfigDict(frozen=True)
    lines: dict[int, LineState]
    blanking: BlankingState


def _parse_status(reply: str) -> ControllerState:
    lines: dict[int, LineState] = {}
    blanking: BlankingState | None = None
    for raw_line in reply.replace("\r", "\n").splitlines():
        text = raw_line.strip()
        if not text or text == "?":
            continue
        if match := _LINE.fullmatch(text):
            line = int(match["line"])
            if line < 1 or line in lines:
                raise MPDSCommunicationError(f"Invalid or duplicate RF line: {line}")
            lines[line] = LineState(
                frequency_mhz=float(match["frequency"]),
                power_dbm=float(match["power"]),
                enabled=match["state"].upper() == "ON",
                input_mode=InputMode(match["mode"].lower()),
            )
        elif match := _BLANKING.fullmatch(text):
            if blanking is not None:
                raise MPDSCommunicationError("Duplicate blanking status")
            blanking = BlankingState(enabled=match[1].upper() == "ON", input_mode=InputMode(match[2].lower()))
        elif not text.startswith(("Temp =", "Alim =", "USB =")):
            raise MPDSCommunicationError(f"Unrecognized MPDS status: {text!r}")
    if not lines or blanking is None or set(lines) != set(range(1, len(lines) + 1)):
        raise MPDSCommunicationError("Incomplete MPDS line or blanking status")
    return ControllerState(lines=lines, blanking=blanking)


class MPDS(Device):
    """Own one connection, shared configuration, and exclusive RF line reservations.

    Construction connects, discovers RF lines, and disables them. Shared operating
    settings are writable properties, applied through rigup defaults or directly.
    Limits must match the controller and attached AOTF. Blanking ON is assumed to
    permit operation in internal mode. Shared settings cannot change while a line
    is reserved. Direct per-line commands remain available for diagnostics.
    """

    __DEVICE_TYPE__ = "aotf"

    def __init__(
        self,
        uid: str,
        port: str,
        *,
        min_frequency_mhz: float,
        max_frequency_mhz: float,
        max_power_dbm: float,
        min_power_dbm: float = 0.0,
        baud: int = 57600,
        timeout_s: float = 0.5,
    ) -> None:
        super().__init__(uid=uid)
        self._validate_limits(min_frequency_mhz, max_frequency_mhz, "frequency")
        self._validate_limits(min_power_dbm, max_power_dbm, "power")
        if min_frequency_mhz <= 0 or min_power_dbm < 0:
            raise ValueError("Frequency must be positive and RF power limits nonnegative")
        if not isfinite(timeout_s) or timeout_s <= 0 or baud <= 0:
            raise ValueError("Serial baud and timeout must be positive and finite")
        self._min_frequency_mhz = min_frequency_mhz
        self._max_frequency_mhz = max_frequency_mhz
        self._min_power_dbm = min_power_dbm
        self._max_power_dbm = max_power_dbm
        self._voltage_range: int | None = None
        self._owners: dict[int, str] = {}
        self._closed = False
        self._shutdown_confirmed = False
        self._faulted = False
        self._transport = SerialTransport(port, baud=baud, timeout=timeout_s)
        try:
            with self.transaction():
                self._transport.ser.write_timeout = timeout_s
                self._transport.drain_input()
                self._num_lines = len(self.get_status().lines)
                for line in range(1, self._num_lines + 1):
                    self.inhibit_line(line)
        except Exception:
            self._transport.close()
            self._closed = True
            raise

    @contextmanager
    def transaction(self) -> Generator[None]:
        """Serialize a complete operation, including optional readback or composition."""
        with self._transport.transaction():
            if self._closed:
                raise RuntimeError("MPDS is closed")
            if self._faulted:
                raise MPDSCommunicationError("MPDS reply framing was lost; close and reconnect")
            yield

    @property
    @describe(label="RF Lines")
    def num_lines(self) -> int:
        return self._num_lines

    @property
    @describe(label="Minimum RF Frequency", units="MHz")
    def min_frequency_mhz(self) -> float:
        return self._min_frequency_mhz

    @property
    @describe(label="Maximum RF Frequency", units="MHz")
    def max_frequency_mhz(self) -> float:
        return self._max_frequency_mhz

    @property
    @describe(label="Minimum RF Power", units="dBm")
    def min_power_dbm(self) -> float:
        return self._min_power_dbm

    @property
    @describe(label="Maximum RF Power", units="dBm")
    def max_power_dbm(self) -> float:
        return self._max_power_dbm

    @numeric_int(options=(5, 10))
    @describe(label="External Voltage Range", units="V")
    def external_voltage_range(self) -> int:
        """Last configured range; unavailable until set because hardware readback is absent."""
        if self._voltage_range is None:
            raise RuntimeError(
                "External voltage range is unknown; set external_voltage_range through defaults or directly"
            )
        return self._voltage_range

    @external_voltage_range.setter
    def external_voltage_range(self, volts: int) -> None:
        """Configure the shared analog range; the command has no acknowledgement."""
        with self.transaction():
            self._ensure_shared_configuration_allowed()
            self._exchange(f"V{int(volts == 10)}".encode() + _EOL, terminator=None)
            self._voltage_range = volts

    @enumerated(options=list(InputMode))
    @describe(label="Blanking Mode")
    def blanking_mode(self) -> str:
        """Read the common blanking input mode from the controller."""
        return self.blanking.input_mode.value

    @blanking_mode.setter
    def blanking_mode(self, value: InputMode | str) -> None:
        mode = InputMode(value)
        with self.transaction():
            self._ensure_shared_configuration_allowed()
            self._exchange(f"L0I{int(mode == InputMode.INTERNAL)}".encode() + _EOL)
            if self.blanking.input_mode != mode:
                raise MPDSCommunicationError("MPDS did not establish requested blanking mode")

    @property
    @describe(label="Blanking Enabled")
    def blanking_enabled(self) -> bool:
        """Read the vendor's common blanking ON/OFF state."""
        return self.blanking.enabled

    @blanking_enabled.setter
    def blanking_enabled(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise ValueError("Blanking enabled must be a boolean")
        with self.transaction():
            self._ensure_shared_configuration_allowed()
            self._exchange(f"L0O{int(value)}".encode() + _EOL)
            if self.blanking.enabled != value:
                raise MPDSCommunicationError("MPDS did not establish requested blanking state")

    @property
    @describe(label="Blanking")
    def blanking(self) -> BlankingState:
        return self.get_status().blanking

    @describe(label="Controller Status")
    def get_status(self) -> ControllerState:
        with self.transaction():
            state = _parse_status(self._exchange(b"S" + _EOL, terminator=b"?"))
            if hasattr(self, "_num_lines") and len(state.lines) != self._num_lines:
                raise MPDSCommunicationError("MPDS status omitted or added RF lines")
            return state

    @describe(label="RF Line Status")
    def get_line(self, line: int) -> LineState:
        self._validate_line(line)
        return self.get_status().lines[line]

    @describe(label="Set RF Frequency")
    def set_frequency(self, line: int, frequency_mhz: float) -> None:
        self._validate_line(line)
        self.validate_frequency(frequency_mhz)
        target = round(frequency_mhz, 3)
        self.validate_frequency(target)
        with self.transaction():
            self._exchange(f"L{line}F{target:07.3f}".encode() + _EOL)
            if abs(self.get_line(line).frequency_mhz - target) > 0.0005:
                raise MPDSCommunicationError("MPDS did not establish requested frequency")

    @describe(label="Set RF Power")
    def set_power(self, line: int, power_dbm: float) -> None:
        self._validate_line(line)
        self.validate_power(power_dbm)
        target = round(power_dbm, 1)
        self.validate_power(target)
        with self.transaction():
            self._exchange(f"L{line}D{target:05.2f}".encode() + _EOL)
            if abs(self.get_line(line).power_dbm - target) > 0.05:
                raise MPDSCommunicationError("MPDS did not establish requested RF power")

    @describe(label="Set RF Line Enabled")
    def set_enabled(self, line: int, enabled: bool) -> None:
        """Set the internal-mode switch; use inhibit_line() to stop external modulation."""
        self._validate_line(line)
        if self._closed and not enabled and self._shutdown_confirmed:
            return
        with self.transaction():
            if self.get_line(line).input_mode != InputMode.INTERNAL:
                raise RuntimeError("RF ON/OFF requires internal mode; use inhibit_line() for external control")
            self._exchange(f"L{line}O{int(enabled)}".encode() + _EOL)
            if self.get_line(line).enabled != enabled:
                raise MPDSCommunicationError("MPDS did not establish requested RF enable state")

    @describe(label="Inhibit RF Line")
    def inhibit_line(self, line: int) -> None:
        """Select internal OFF, allowing the manual's typical 100 ms for mode changes."""
        self._validate_line(line)
        if self._closed and self._shutdown_confirmed:
            return
        with self.transaction():
            state = self.get_line(line)
            self._exchange(f"L{line}O0I1".encode() + _EOL)
            if state.input_mode != InputMode.INTERNAL:
                sleep(0.1)
            state = self.get_line(line)
            if state.input_mode != InputMode.INTERNAL or state.enabled:
                raise MPDSCommunicationError("MPDS did not establish internal OFF")

    @describe(label="Set RF Input Mode")
    def set_input_mode(self, line: int, mode: InputMode | str) -> None:
        self._validate_line(line)
        mode = InputMode(mode)
        with self.transaction():
            state = self.get_line(line)
            if state.input_mode == mode:
                return
            if state.enabled or state.input_mode == InputMode.EXTERNAL:
                raise RuntimeError("Disable the RF line before changing its input mode")
            self._exchange(f"L{line}I{int(mode == InputMode.INTERNAL)}".encode() + _EOL)
            sleep(0.1)
            if self.get_line(line).input_mode != mode:
                raise MPDSCommunicationError("MPDS did not establish requested input mode")

    def reserve_line(self, line: int, owner: str) -> None:
        """Reserve a line exclusively, including against duplicate construction by one UID."""
        self._validate_line(line)
        with self.transaction():
            if line in self._owners:
                raise ValueError(f"RF line {line} is already reserved by {self._owners[line]!r}")
            self._owners[line] = owner

    def release_line(self, line: int, owner: str) -> None:
        """Release a reservation after successful inhibition; also usable after shutdown."""
        with self._transport.transaction():
            if self._owners.get(line) != owner:
                raise ValueError(f"RF line {line} is not reserved by {owner!r}")
            del self._owners[line]

    def validate_frequency(self, value: float) -> None:
        if not isfinite(value) or not self.min_frequency_mhz <= value <= self.max_frequency_mhz:
            raise ValueError("RF frequency is outside configured limits")

    def validate_power(self, value: float) -> None:
        if not isfinite(value) or not self.min_power_dbm <= value <= self.max_power_dbm:
            raise ValueError("RF power is outside configured limits")

    def close(self) -> None:
        """Attempt to inhibit every line, release the connection, and report any failures."""
        with self._transport.transaction():
            if self._closed:
                return
            errors: list[Exception] = []
            for line in range(1, self._num_lines + 1):
                try:
                    self.inhibit_line(line)
                except Exception as error:
                    errors.append(error)
            self._shutdown_confirmed = not errors
            self._transport.close()
            self._closed = True
            if errors:
                raise ExceptionGroup("MPDS shutdown could not confirm all lines disabled", errors)

    def _exchange(self, payload: bytes, *, terminator: bytes | None = _EOL) -> str:
        """Exchange within a transaction; never retry a command after an uncertain reply."""
        try:
            return self._write_read(payload, terminator)
        except (SerialException, UnicodeError, MPDSCommunicationError) as error:
            self._faulted = True
            raise MPDSCommunicationError(f"MPDS exchange failed for {payload!r}: {error}") from error

    def _write_read(self, payload: bytes, terminator: bytes | None) -> str:
        with self._transport.transaction() as port:
            if port.write(payload) != len(payload):
                raise MPDSCommunicationError("Incomplete MPDS command write")
            if terminator is None:
                return ""
            reply = port.read_until(terminator, size=_MAX_REPLY_BYTES)
            if not reply.endswith(terminator):
                raise MPDSCommunicationError("Incomplete MPDS reply")
            return reply[: -len(terminator)].decode("ascii")

    def _ensure_shared_configuration_allowed(self) -> None:
        if self._owners or any(line.enabled for line in self.get_status().lines.values()):
            raise RuntimeError("Shared MPDS configuration requires no reserved or enabled RF lines")

    def _validate_line(self, line: int) -> None:
        if isinstance(line, bool) or not isinstance(line, int) or not 1 <= line <= self._num_lines:
            raise ValueError(f"RF line must be an integer in 1..{self._num_lines}")

    @staticmethod
    def _validate_limits(lower: float, upper: float, name: str) -> None:
        if not isfinite(lower) or not isfinite(upper) or lower >= upper:
            raise ValueError(f"RF {name} limits must be finite and increasing")
