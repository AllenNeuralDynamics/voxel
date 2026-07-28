"""Shared serial connection for a stack of Micronix MMC-100 controllers."""

import threading
from collections.abc import Iterator

from vxl_drivers.axes.mmc._cmds import Cmd, format_number
from vxl_drivers.serial import SerialTransport

from rigup import Device

DEFAULT_BAUD = 38400
DEFAULT_TIMEOUT_S = 0.5
TERMINATOR = b"\r"


class MMCCommunicationError(ConnectionError):
    """Communication with an MMC controller failed."""


class MMCAxisAlreadyReservedError(ValueError):
    """An MMC axis address is already owned by another driver instance."""


class MMCHub(Device):
    """Own one serial bus shared by one or more addressed MMC axes."""

    def __init__(
        self,
        port: str,
        *,
        uid: str = "mmc",
        baud: int = DEFAULT_BAUD,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        super().__init__(uid=uid)
        self._transport = SerialTransport(port=port, baud=baud, timeout=timeout_s)
        self._timeout_s = timeout_s
        self._reserved: set[int] = set()
        self._reservation_lock = threading.Lock()

        # The controller can emit startup text. It never emits unsolicited runtime
        # messages, so discarding that text once is safe.
        with self._transport.transaction() as serial_port:
            serial_port.reset_input_buffer()

    def command(self, axis_id: int, command: Cmd, *parameters: str | float) -> None:
        """Send a command that does not produce a response."""
        payload = self._frame(axis_id, command, parameters)
        try:
            with self._transport.transaction() as serial_port:
                serial_port.write(payload)
                serial_port.flush()
        except Exception as exc:
            raise MMCCommunicationError(
                f"MMC command failed for axis {axis_id}: {payload.decode('ascii').strip()!r}"
            ) from exc

    def query(self, axis_id: int, command: Cmd) -> str:
        """Run a single-line query and return its final nonempty response line."""
        lines = self.query_lines(axis_id, command)
        return lines[-1]

    def query_lines(self, axis_id: int, command: Cmd) -> tuple[str, ...]:
        """Run a query and return every response line through the final carriage return."""
        return self._query_lines(axis_id, command, timeout_s=self._timeout_s)

    def blocking_query(self, axis_id: int, command: Cmd, *, timeout_s: float | None) -> str:
        """Run a query that may legitimately block until a controller operation completes."""
        lines = self._query_lines(axis_id, command, timeout_s=timeout_s)
        return lines[-1]

    def _query_lines(self, axis_id: int, command: Cmd, *, timeout_s: float | None) -> tuple[str, ...]:
        payload = self._frame(axis_id, command, ("?",))
        try:
            with self._transport.transaction() as serial_port:
                serial_port.reset_input_buffer()
                serial_port.write(payload)
                serial_port.flush()
                previous_timeout = serial_port.timeout
                try:
                    serial_port.timeout = timeout_s
                    raw = serial_port.read_until(TERMINATOR)
                finally:
                    serial_port.timeout = previous_timeout
        except Exception as exc:
            raise MMCCommunicationError(
                f"MMC query failed for axis {axis_id}: {payload.decode('ascii').strip()!r}"
            ) from exc

        lines = tuple(self._clean_lines(raw))
        if not lines:
            raise MMCCommunicationError(
                f"MMC query returned no response for axis {axis_id}: {payload.decode('ascii').strip()!r}"
            )
        return lines

    def reserve_axis(self, axis_id: int) -> None:
        self._validate_axis_id(axis_id)
        with self._reservation_lock:
            if axis_id in self._reserved:
                raise MMCAxisAlreadyReservedError(f"MMC axis {axis_id} is already reserved on {self.uid}")
            self._reserved.add(axis_id)

    def release_axis(self, axis_id: int) -> None:
        with self._reservation_lock:
            self._reserved.discard(axis_id)

    def close(self) -> None:
        self._transport.close()

    @staticmethod
    def _frame(axis_id: int, command: Cmd, parameters: tuple[str | int | float, ...]) -> bytes:
        MMCHub._validate_axis_id(axis_id)
        suffix = ",".join(format_number(value) if isinstance(value, int | float) else value for value in parameters)
        return f"{axis_id}{command.value}{suffix}".encode("ascii") + TERMINATOR

    @staticmethod
    def _clean_lines(raw: bytes) -> Iterator[str]:
        decoded = raw.decode("ascii", errors="replace").replace("\r", "\n")
        for line in decoded.splitlines():
            cleaned = line.strip().removeprefix("#").strip()
            if cleaned:
                yield cleaned

    @staticmethod
    def _validate_axis_id(axis_id: int) -> None:
        if not 1 <= axis_id <= 99:
            raise ValueError(f"MMC axis_id must be in range 1..99, got {axis_id}")
