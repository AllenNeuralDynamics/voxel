"""Serial link to Coherent OBIS lasers with handshaking: every command ends in OK or ERR-<code>."""

from collections.abc import Generator
from contextlib import contextmanager
from math import isfinite

from serial import SerialException

from vxl_drivers.serial import SerialTransport

_EOL = b"\r\n"
_MAX_REPLY_LINES = 16
_SETUP_QUIET_S = 0.2
# Codes collected from other OBIS drivers; the operator's manual (P/N 2283534) has the full table.
_ERRORS = {
    "ERR-100": "unrecognized command",
    "ERR-101": "invalid command",
    "ERR-102": "invalid parameter or value out of range",
    "ERR-241": "device unavailable",
    "ERR-350": "queue overflow",
}


class ObisError(ConnectionError):
    """A rejected command, invalid reply, or lost framing; code holds any ERR-<n> reply."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class ObisLink:
    """Own one serial port and serialize complete exchanges; not a device."""

    def __init__(self, port: str, *, baud: int = 115200, timeout_s: float = 1.0) -> None:
        if baud <= 0 or not isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("baud and timeout must be positive")
        self._closed = False
        self._faulted = False
        self._transport = SerialTransport(port, baud=baud, timeout=timeout_s)
        try:
            self._transport.ser.write_timeout = timeout_s
            self._start_handshaking()
        except Exception:
            self.close()
            raise

    def _start_handshaking(self) -> None:
        # The reply format before handshaking is unknown, so discard whatever these setup commands return.
        # TODO: verify on real hardware that SYST:COMM:PROM OFF and SYST:COMM:HAND ON need no other reply handling.
        with self._transport.transaction() as port:
            self._transport.drain_input()
            for setup in ("SYST:COMM:PROM OFF", "SYST:COMM:HAND ON"):
                port.write(f"{setup}\r\n".encode("ascii"))
                self._transport.drain_input(quiet_s=_SETUP_QUIET_S)
        if not self.flag("SYST:COMM:HAND?"):
            raise ObisError("OBIS did not enable handshaking")

    @contextmanager
    def transaction(self) -> Generator[None]:
        """Serialize a complete operation, including readbacks."""
        with self._transport.transaction():
            if self._closed:
                raise RuntimeError("OBIS link is closed")
            if self._faulted:
                raise ObisError("OBIS reply framing was lost; reconnect")
            yield

    @property
    def is_closed(self) -> bool:
        return self._closed

    def command(self, message: str) -> None:
        if lines := self._exchange(message):
            raise ObisError(f"Unexpected reply to {message!r}: {lines!r}")

    def query(self, message: str) -> str:
        lines = self._exchange(message)
        if len(lines) != 1:
            raise ObisError(f"Expected one reply line for {message!r}, got {lines!r}")
        return lines[0]

    def number(self, message: str, *, suffix: str = "") -> float:
        reply = self.query(message)
        try:
            value = float(reply.removesuffix(suffix))
        except ValueError as error:
            raise ObisError(f"Expected a number for {message!r}, got {reply!r}") from error
        if not isfinite(value):
            raise ObisError(f"OBIS returned a nonfinite number for {message!r}")
        return value

    def flag(self, message: str) -> bool:
        reply = self.query(message).upper()
        if reply not in ("ON", "OFF"):
            raise ObisError(f"Expected ON or OFF for {message!r}, got {reply!r}")
        return reply == "ON"

    def set_emission(self, address: str, enabled: bool) -> None:
        """Switch SOUR<address>:AM:STAT and verify the readback."""
        state = "ON" if enabled else "OFF"
        with self.transaction():
            self.command(f"SOUR{address}:AM:STAT {state}")
            # TODO: verify on real hardware that the readback is ON during the 5 s CDRH delay.
            if self.flag(f"SOUR{address}:AM:STAT?") != enabled:
                raise ObisError(f"OBIS did not switch emission {state}; check the key and interlock")

    def close(self) -> None:
        with self._transport.transaction():
            if not self._closed:
                self._transport.close()
                self._closed = True

    def _exchange(self, message: str) -> list[str]:
        """Return the reply lines before OK; never retry after an uncertain reply."""
        with self.transaction():
            try:
                lines = self._write_read(message)
            except (SerialException, UnicodeError, ObisError) as error:
                self._faulted = True
                raise ObisError(f"Exchange failed for {message!r}: {error}") from error
        if (last := lines[-1]).startswith("ERR"):
            raise ObisError(f"OBIS rejected {message!r}: {last} ({_ERRORS.get(last, 'see the manual')})", code=last)
        return lines[:-1]

    def _write_read(self, message: str) -> list[str]:
        with self._transport.transaction() as port:
            payload = f"{message}\r\n".encode("ascii")
            if port.write(payload) != len(payload):
                raise ObisError("Incomplete command write")
            lines: list[str] = []
            while len(lines) < _MAX_REPLY_LINES:
                raw = port.read_until(_EOL, size=4096)
                if not raw.endswith(_EOL):
                    raise ObisError("Incomplete OBIS reply")
                line = raw[: -len(_EOL)].decode("ascii").strip()
                lines.append(line)
                if line == "OK" or line.startswith("ERR"):
                    return lines
            raise ObisError("OBIS reply did not end with OK")
