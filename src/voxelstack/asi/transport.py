import threading

import serial


class SerialTransport:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.5):
        self.ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)
        self._lock = threading.Lock()

    def write(self, b: bytes) -> None:
        with self._lock:
            self.ser.write(b)

    def readline(self) -> bytes | None:
        line = self.ser.readline()
        return line if line else None

    def close(self) -> None:
        if self.ser.is_open:
            self.ser.close()
