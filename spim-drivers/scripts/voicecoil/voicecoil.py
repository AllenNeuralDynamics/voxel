import time

import serial
from rich import print

BAUD = 115200
TIMEOUT = 1.25


class VoiceCoilDevice:
    def __init__(self, port: str | None = None, baudrate: int = BAUD):
        self._ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=TIMEOUT,
            write_timeout=TIMEOUT,
            rtscts=False,
            dsrdtr=False,
            xonxoff=False,
        )
        self.reset()

    def reset(self):
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()
        self._ser.flush()
        self._send('d0')

    def _send_bytes(self, cmd: bytes) -> bytes:
        print(f'Sending command: [green]{cmd}[/green]')
        try:
            self._ser.write(cmd)
        except serial.SerialTimeoutException as e:
            print(f'[red]Communication Error: {e}[/red]')
            raise UserWarning('Failed to write to serial port.') from e
        time.sleep(TIMEOUT * 2)
        data = self._ser.read(9999)
        if len(data) > 0:
            print(f'Received command: [green]{data.decode()}[/green]')
            return data
        return b''

    def _send(self, msg: str) -> bytes:
        msg = msg.strip() + '\r'
        return self._send_bytes(msg.encode('utf-8'))

    def get_info(self) -> bytes:
        return self._send('N')

    def enable(self) -> bytes:
        return self._send('k1')

    def disable(self) -> bytes:
        return self._send('k0')

    def test(self) -> bytes:
        return self._send_bytes(b'd0\r')

    def close(self):
        self._ser.close()
