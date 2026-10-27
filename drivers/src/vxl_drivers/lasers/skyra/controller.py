"""Shared serial connection to a Cobolt Skyra, with one reservation per laser line."""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from math import isfinite
from time import monotonic, sleep

from serial import SerialException

from rigup import Device, describe
from vxl_drivers.serial import SerialTransport

_LINES = range(1, 5)
_REJECTED = "Syntax error"
# pycobolt, the vendor library, waits 100 ms between commands.
_COMMAND_GAP_S = 0.1
_OPERATING_STATES = {
    "0": "off",
    "1": "waiting for temperature",
    "2": "waiting for key",
    "3": "warming up",
    "4": "completed",
    "5": "fault",
    "6": "aborted",
}
_FAULTS = {"0": "none", "1": "temperature error", "3": "interlock open", "4": "constant power fault"}


class SkyraError(ConnectionError):
    """A rejected command, missing reply, or failed readback."""


class SkyraController(Device):
    """Own the Skyra port, discover its lines, and reserve each line for one SkyraSource."""

    __DEVICE_TYPE__ = "laser_controller"

    def __init__(self, uid: str, port: str, *, baud: int = 115200, timeout_s: float = 1.0) -> None:
        super().__init__(uid=uid)
        if baud <= 0 or not isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("baud and timeout must be positive")
        self._lock = threading.RLock()
        self._owners: dict[int, str] = {}
        self._confirmed_off: set[int] = set()
        self._closed = False
        self._replied_at = 0.0
        self._transport = SerialTransport(port, baud=baud, timeout=timeout_s)
        try:
            self._transport.ser.write_timeout = timeout_s
            self._serial_number = self.query("sn?")
            self._lines = self._discover()
        except Exception:
            self._transport.close()
            self._closed = True
            raise

    # TODO: verify on real hardware what an empty line replies to #glw?; the manual does not say.
    def _discover(self) -> dict[int, float]:
        lines: dict[int, float] = {}
        for line in _LINES:
            reply = self._exchange(f"{line}glw?")
            try:
                wavelength = float(reply)
            except ValueError:
                continue
            if isfinite(wavelength) and wavelength > 0:
                lines[line] = wavelength
        if not lines:
            raise SkyraError("No laser lines found on the Skyra")
        return lines

    @contextmanager
    def transaction(self) -> Generator[None]:
        """Serialize a complete operation, including readbacks."""
        with self._transport.transaction():
            if self._closed:
                raise RuntimeError("Skyra controller is closed")
            yield

    def command(self, message: str) -> None:
        if (reply := self.query(message)) != "OK":
            raise SkyraError(f"Skyra replied {reply!r} to {message!r}")

    def query(self, message: str) -> str:
        reply = self._exchange(message)
        if reply.startswith(_REJECTED):
            raise SkyraError(f"Skyra rejected {message!r}: {reply}")
        return reply

    def number(self, message: str) -> float:
        reply = self.query(message)
        try:
            value = float(reply)
        except ValueError as error:
            raise SkyraError(f"Expected a number for {message!r}, got {reply!r}") from error
        if not isfinite(value):
            raise SkyraError(f"Skyra returned a nonfinite number for {message!r}")
        return value

    def flag(self, message: str) -> bool:
        reply = self.query(message)
        if reply not in ("0", "1"):
            raise SkyraError(f"Expected 0 or 1 for {message!r}, got {reply!r}")
        return reply == "1"

    def set_line(self, line: int, on: bool) -> None:
        """Switch one line on or off and verify the readback."""
        with self.transaction():
            self.command(f"{line}l{int(on)}")
            if self.flag(f"{line}l?") != on:
                state = "on" if on else "off"
                raise SkyraError(
                    f"Skyra line {line} did not switch {state}; state: {self.operating_state}, fault: {self.fault}"
                )

    @property
    @describe(label="Installed Lines")
    def installed_lines(self) -> dict[int, float]:
        """Line-to-wavelength mapping in nm, discovered at connection time."""
        return dict(self._lines)

    @property
    @describe(label="Reserved Lines")
    def reserved_lines(self) -> list[int]:
        with self._lock:
            return list(self._owners)

    @property
    @describe(label="Serial Number")
    def serial_number(self) -> str:
        return self._serial_number

    @property
    @describe(label="Operating State")
    def operating_state(self) -> str:
        """Autostart state from gom?."""
        reply = self.query("gom?")
        return _OPERATING_STATES.get(reply, f"unknown ({reply})")

    @property
    @describe(label="Fault")
    def fault(self) -> str:
        reply = self.query("f?")
        return _FAULTS.get(reply, f"unknown ({reply})")

    @property
    @describe(label="Key Switch On")
    def key_switch_on(self) -> bool:
        return self.flag("@cobasks?")

    @property
    @describe(label="Interlock")
    def interlock(self) -> str:
        """Reply to ilk?, unparsed until its meaning is confirmed."""
        # TODO: verify on real hardware which ilk? value means closed; the manual says both.
        return self.query("ilk?")

    @property
    @describe(label="Operating Hours", units="h")
    def operating_hours(self) -> float:
        return self.number("hrs?")

    @describe(label="Clear Fault")
    def clear_fault(self) -> None:
        self.command("cf")

    def reserve(self, line: int, owner: str) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("Skyra controller is closed")
            if line not in self._lines:
                raise ValueError(f"Line {line} has no discovered laser")
            if line in self._owners:
                raise ValueError(f"Line {line} is already reserved by {self._owners[line]!r}")
            self._owners[line] = owner

    def release(self, line: int, owner: str) -> None:
        """Release after successful borrower shutdown, including after controller close."""
        with self._lock:
            if self._owners.get(line) != owner:
                raise ValueError(f"Line {line} is not reserved by {owner!r}")
            del self._owners[line]

    def confirmed_off(self, line: int) -> bool:
        """Whether controller shutdown confirmed this line off."""
        return self._closed and line in self._confirmed_off

    def close(self) -> None:
        """Try to stop every reserved line, close the port, and report all failures."""
        with self._lock, self._transport.transaction():
            if self._closed:
                return
            errors: list[Exception] = []
            for line in self._owners:
                try:
                    self.set_line(line, False)
                    self._confirmed_off.add(line)
                except Exception as error:
                    errors.append(error)
            self._transport.close()
            self._closed = True
            if errors:
                raise ExceptionGroup("Skyra controller shutdown failed", errors)

    def _exchange(self, message: str) -> str:
        """Return the raw reply line; replies end in CR, so a trailing LF is drained before the next write."""
        with self.transaction(), self._transport.transaction() as port:
            if (remaining := self._replied_at + _COMMAND_GAP_S - monotonic()) > 0:
                sleep(remaining)
            self._transport.drain_input()
            try:
                port.write(f"{message}\r".encode("ascii"))
                raw = port.read_until(b"\r", size=4096)
            except SerialException as error:
                raise SkyraError(f"Serial error for {message!r}: {error}") from error
            finally:
                self._replied_at = monotonic()
        if not raw.endswith(b"\r"):
            raise SkyraError(f"No reply from Skyra to {message!r}; check the port and baud")
        return raw.decode("ascii", errors="replace").strip()
