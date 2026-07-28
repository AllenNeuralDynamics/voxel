import logging
import threading
from collections.abc import Generator
from contextlib import contextmanager

import serial

logger = logging.getLogger("serial transport")


class SerialTransport:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.5):
        self.ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)
        self._lock = threading.Lock()

    @contextmanager
    def transaction(self) -> Generator[serial.Serial]:
        """Hold exclusive access to the serial port for a protocol transaction."""
        with self._lock:
            yield self.ser

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
