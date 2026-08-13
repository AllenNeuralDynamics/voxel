import logging
import threading
from collections.abc import Generator
from contextlib import contextmanager

import serial

logger = logging.getLogger("serial transport")


class SerialTransport:
    # Floor for the silence window. Sub-millisecond waits are not reliably observable through OS
    # timer granularity, so a computed byte time below this is rounded up to it.
    _MIN_QUIET_S = 0.002
    # How many byte times of silence mean a transmission has genuinely stopped rather than paused.
    _QUIET_BYTE_TIMES = 4

    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.5):
        self.ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)
        # Reentrant so the helpers below can be called from inside `transaction()`, which is where
        # a protocol layer holding the port needs them.
        self._lock = threading.RLock()

    @contextmanager
    def transaction(self) -> Generator[serial.Serial]:
        """Hold exclusive access to the serial port for a protocol transaction."""
        with self._lock:
            yield self.ser

    @property
    def quiet_window_s(self) -> float:
        """How long the line must stay silent before pending input is considered complete."""
        byte_time = 10.0 / self.ser.baudrate  # 8 data bits plus start and stop
        return max(self._MIN_QUIET_S, byte_time * self._QUIET_BYTE_TIMES)

    def drain_input(self, quiet_s: float | None = None) -> int:
        """Discard pending input until the line has been silent for `quiet_s`, returning the count.

        `reset_input_buffer` only drops bytes that have *already arrived*. Purging and immediately
        writing lets bytes still in flight land at the head of the next reply, splicing one reply
        onto another. Waiting for real silence is what proves nothing further is coming.

        Safe to call while holding `transaction()`.
        """
        window = self.quiet_window_s if quiet_s is None else quiet_s
        discarded = 0
        with self._lock:
            previous, self.ser.timeout = self.ser.timeout, window
            try:
                while chunk := self.ser.read(max(1, self.ser.in_waiting)):
                    discarded += len(chunk)
            finally:
                self.ser.timeout = previous
        return discarded

    def write(self, b: bytes) -> None:
        with self._lock:
            self.ser.write(b)

    def readline(self) -> bytes | None:
        with self._lock:
            line = self.ser.readline()
        return line or None

    # Might have to switch to this if bugs are present
    def readline2(self) -> bytes | None:
        with self._lock:
            buf = self.ser.read_until(b"\r")
        return buf or None

    def close(self) -> None:
        with self._lock:
            if self.ser.is_open:
                self.ser.close()
                logger.debug("Serial port closed. port: %s", self.ser.port)
