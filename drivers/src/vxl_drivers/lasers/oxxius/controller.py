"""Shared serial connection for L4Cc/L6Cc laser drivers.

Register OxxiusController on the same rig node as its borrowers and pass its UID
as their controller argument. The controller discovers slots without changing
emission, reserves each slot for one borrower, and serializes complete operations.
Close attempts to stop every reserved source before releasing the port. Borrowers
release reservations only after a successful stop and never close this connection.

Protocol: 9600 baud, 8N1, CR commands and CRLF replies, following voxel-classic's
oxxius/lxcc.py. Writes require OK, followed by explicit readback where available.
No automatic retry follows an uncertain reply. A framing failure faults the link.

Hardware checks before adoption:
- Confirm CRLF framing, OK acknowledgements, and empty-slot 'Not authorized' replies.
- Confirm Ln INF? discovery and slot identity against the Manufacturing Test Report.
- Check LBX L/?L and LCX T/?T with TTL held high and low; neither is an optical meter.
- LCX T shutdown differs from legacy L: the LnCc manual documents T for LCX emission.
- Confirm source-addressed AM/TTL reaches an LCX's linked AOM on this firmware.
- Shared SHn shutters address output ports, not laser slots; this driver never changes them.

References: voxel-classic/src/voxel/devices/controller/oxxius/lxcc.py and Oxxius
LnCc user manual, pp. 85-95 (https://manualzz.com/doc/78988076/oxxius-laser-combiner-l6cc-user-manual).
"""

from collections.abc import Generator
from contextlib import contextmanager
from enum import StrEnum
from math import isclose, isfinite
from typing import Literal, override

from serial import SerialException

from rigup import Device, describe
from vxl_drivers.serial import SerialTransport


class Cmd(StrEnum):
    """Source-addressed commands; current setting uses percent of nominal current."""

    CURRENT_CONTROL = "ACC"
    ANALOG = "AM"
    DIGITAL = "TTL"
    EMISSION = "L"
    CURRENT = "CM"
    POWER = "P"
    TEMPERATURE_REGULATION = "T"


class Query(StrEnum):
    """Source-addressed queries; current readback uses mA."""

    MODEL = "INF?"
    CURRENT_CONTROL = "?ACC"
    ANALOG = "?AM"
    DIGITAL = "?TTL"
    EMISSION = "?L"
    CURRENT_SETPOINT = "?SC"
    POWER_SETPOINT = "?SP"
    MAX_POWER = "?MAXLP"
    POWER = "?P"
    TEMPERATURE = "?BT"
    TEMPERATURE_REGULATION = "?T"
    FAULT = "?F"


class OxxiusCommunicationError(ConnectionError):
    """A rejected command, invalid reply, or failed readback."""


class OxxiusController(Device):
    """Own the serial connection and exclusive reservations of populated slots."""

    __DEVICE_TYPE__ = "laser_controller"

    def __init__(
        self, uid: str, port: str, *, model: Literal["L4cc", "L6cc"] = "L6cc", baud: int = 9600, timeout_s: float = 1.0
    ) -> None:
        super().__init__(uid=uid)
        if model not in ("L4cc", "L6cc"):
            raise ValueError("model must be L4cc or L6cc")
        if baud <= 0 or not isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("baud and timeout must be positive")
        self._slots = 4 if model == "L4cc" else 6
        self._models: dict[str, str] = {}
        self._owners: dict[str, tuple[str, Cmd]] = {}
        self._shutdown: set[str] = set()
        self._closed = False
        self._faulted = False
        self._transport = SerialTransport(port, baud=baud, timeout=timeout_s)
        try:
            self._transport.ser.write_timeout = timeout_s
            self._transport.drain_input()
            for slot in range(1, self._slots + 1):
                prefix = f"L{slot}"
                reply = self._exchange(f"{prefix} INF?", allow_absent=True)
                if reply.casefold() != "not authorized":
                    self._models[prefix] = reply
        except Exception:
            self._transport.close()
            self._closed = True
            raise

    @contextmanager
    def transaction(self) -> Generator[None]:
        """Serialize a complete operation, including readbacks and startup waits."""
        with self._transport.transaction():
            if self._closed:
                raise RuntimeError("Oxxius controller is closed")
            if self._faulted:
                raise OxxiusCommunicationError("Oxxius reply framing was lost; reconnect the controller")
            yield

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    @describe(label="Installed Sources")
    def installed_sources(self) -> dict[str, str]:
        """Slot-to-model mapping discovered at connection time."""
        return dict(self._models)

    @property
    @describe(label="Reserved Sources")
    def reserved_sources(self) -> list[str]:
        with self._transport.transaction():
            return list(self._owners)

    def reserve(self, prefix: str, owner: str, *, family: Literal["LBX", "LCX"]) -> str:
        """Claim a matching source and select its documented shutdown command."""
        prefix = prefix.upper()
        with self.transaction():
            if prefix not in self._models or not self._models[prefix].upper().startswith(family):
                raise ValueError(f"{prefix} is not a discovered {family} source")
            if prefix in self._owners:
                raise ValueError(f"{prefix} is already reserved")
            stop = Cmd.EMISSION if family == "LBX" else Cmd.TEMPERATURE_REGULATION
            self._owners[prefix] = (owner, stop)
        return prefix

    def release(self, prefix: str, owner: str) -> None:
        """Release after successful borrower shutdown, including after controller close."""
        with self._transport.transaction():
            if self._owners[prefix][0] != owner:
                raise ValueError(f"{prefix} is not reserved by {owner}")
            del self._owners[prefix]

    def query(self, query: Query, prefix: str) -> str:
        self._validate_prefix(prefix)
        return self._exchange(f"{prefix} {query.value}")

    def number(self, query: Query, prefix: str) -> float:
        return self._number(self.query(query, prefix))

    def flag(self, query: Query, prefix: str) -> bool:
        reply = self.query(query, prefix)
        if reply not in ("0", "1"):
            raise OxxiusCommunicationError(f"Expected 0 or 1 for {prefix} {query}, got {reply!r}")
        return reply == "1"

    def command(self, command: Cmd, value: float, prefix: str) -> None:
        self._validate_prefix(prefix)
        if not isfinite(value):
            raise ValueError("command value must be finite")
        self._ack(f"{prefix} {command.value} {value:g}")

    def set_flag(self, command: Cmd, query: Query, value: bool, prefix: str) -> None:
        with self.transaction():
            self.command(command, int(value), prefix)
            if self.flag(query, prefix) != value:
                raise OxxiusCommunicationError(f"{prefix} did not establish {command}={int(value)}")

    def linked_power(self, prefix: str) -> float:
        """Read the linked modulator setpoint in optical mW, not measured output."""
        self._validate_prefix(prefix)
        return self._number(self._exchange(f"?PL{prefix[1:]}"))

    def set_linked_power(self, prefix: str, value: float) -> None:
        self._validate_prefix(prefix)
        if not isfinite(value) or value < 0:
            raise ValueError("linked power must be finite and nonnegative")
        with self.transaction():
            self._ack(f"PL{prefix[1:]} {value:.1f}")
            if not isclose(self.linked_power(prefix), value, rel_tol=0, abs_tol=0.051):
                raise OxxiusCommunicationError("Linked power readback differs from the requested setting")

    def is_enabled(self, prefix: str) -> bool:
        stop = self._owners[prefix][1]
        query = Query.EMISSION if stop == Cmd.EMISSION else Query.TEMPERATURE_REGULATION
        return self.flag(query, prefix)

    def enable(self, prefix: str) -> None:
        with self.transaction():
            self.command(self._owners[prefix][1], 1, prefix)
            if not self.is_enabled(prefix):
                raise OxxiusCommunicationError(f"{prefix} did not enable its emission permission")

    def disable(self, prefix: str) -> None:
        """Stop one reserved source and verify its control flag."""
        if self._closed and prefix in self._shutdown:
            return
        with self.transaction():
            self.command(self._owners[prefix][1], 0, prefix)
            if self.is_enabled(prefix):
                raise OxxiusCommunicationError(f"{prefix} did not disable its emission permission")

    def _ack(self, message: str) -> None:
        reply = self._exchange(message)
        if reply != "OK":
            raise OxxiusCommunicationError(f"Expected OK for {message!r}, got {reply!r}")

    def _exchange(self, message: str, *, allow_absent: bool = False) -> str:
        with self.transaction():
            try:
                text = self._write_read(message)
            except (SerialException, UnicodeError, OxxiusCommunicationError) as error:
                self._faulted = True
                raise OxxiusCommunicationError(f"Exchange failed for {message!r}: {error}") from error
            if not text or text.startswith(("?", "ERR")) or (text.casefold() == "not authorized" and not allow_absent):
                raise OxxiusCommunicationError(f"Oxxius rejected {message!r}: {text!r}")
            return text

    def _write_read(self, message: str) -> str:
        with self._transport.transaction() as port:
            payload = (message + "\r").encode("ascii")
            if port.write(payload) != len(payload):
                raise OxxiusCommunicationError("Incomplete command write")
            reply = port.read_until(b"\r\n", size=4096)
            if not reply.endswith(b"\r\n"):
                raise OxxiusCommunicationError("Incomplete Oxxius reply")
            return reply[:-2].decode("ascii").strip()

    def _validate_prefix(self, prefix: str) -> None:
        if prefix not in self._models:
            raise ValueError(f"Unknown source slot {prefix!r}")

    @staticmethod
    def _number(text: str) -> float:
        try:
            value = float(text)
        except ValueError as error:
            raise OxxiusCommunicationError(f"Expected a numeric reply, got {text!r}") from error
        if not isfinite(value):
            raise OxxiusCommunicationError("Oxxius returned a nonfinite number")
        return value

    @override
    def close(self) -> None:
        """Try every reserved source stop, close the port, and report all failures."""
        with self._transport.transaction():
            if self._closed:
                return
            errors: list[Exception] = []
            for prefix in self._owners:
                try:
                    self.disable(prefix)
                    self._shutdown.add(prefix)
                except Exception as error:
                    errors.append(error)
            self._transport.close()
            self._closed = True
            if errors:
                raise ExceptionGroup("Oxxius controller shutdown failed", errors)
