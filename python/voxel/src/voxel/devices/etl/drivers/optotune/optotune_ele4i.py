import struct
from typing import Any

import serial
from voxel.devices.etl import ETLControlMode, VoxelTunableLens

# constants for Optotune EL-E-4i controller

MODES = {
    ETLControlMode.EXTERNAL: ['MwDA', '>xxx'],
    ETLControlMode.INTERNAL: ['MwCA', '>xxxBhh'],
}


def crc_16(s: bytes) -> int:
    crc = 0x0000
    for c in s:
        crc = crc ^ c
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) > 0 else crc >> 1

    return crc


class OptotuneELE4ITunableLens(VoxelTunableLens):
    def __init__(self, name: str, port: str):
        super().__init__(name)

        self.debug = False

        self._ser = serial.Serial(port=port, baudrate=115200, timeout=1)
        self._ser.flush()
        res = self._send_command('X', '>x8s')
        if res:
            try:
                self.serial_number = res[0].decode('ascii')
            except IndexError:
                self.log.exception('Error reading serial number: %s', res)

    @property
    def mode(self) -> ETLControlMode:
        """Get the tunable lens control mode."""
        mode = ETLControlMode.UNKNOWN
        if res := self._send_command('MMA', '>xxxB'):
            mode_ranges: dict[int, ETLControlMode] = {
                1: ETLControlMode.INTERNAL,
                2: ETLControlMode.EXTERNAL,
                3: ETLControlMode.EXTERNAL,
                4: ETLControlMode.EXTERNAL,
                5: ETLControlMode.EXTERNAL,
            }
            try:
                res = res[0]
                mode = mode_ranges.get(res, ETLControlMode.UNKNOWN)
                self.log.debug('Mode: %s', mode)
            except IndexError:
                self.log.exception('Error reading mode: %s', res)
        return mode

    @mode.setter
    def mode(self, mode: ETLControlMode):
        """Set the tunable lens control mode."""
        mode_list = MODES[mode]
        self._send_command(mode_list[0], mode_list[1])

    @property
    def temperature_c(self) -> float:
        """Get the temperature in deg C."""
        temp: float = -9999.0
        if temp_res := self._send_command('TCA', '>xxxh'):
            try:
                temp = temp_res[0] * 0.0625 if temp_res else temp
                self.log.debug('Temperature: %s', temp)
            except IndexError:
                self.log.exception('Error reading temperature: %s', temp_res)

        return temp

    def _send_command(self, command: str | bytes, reply_fmt: str | None = None) -> tuple[Any, ...] | None:
        command = bytes(command, encoding='ascii') if isinstance(command, str) else bytes(command)
        command += struct.pack('<H', crc_16(command))
        if self.debug:
            commandhex = ' '.join(f'{c:02x}' for c in command)
            print(f'{commandhex:<50} ¦ {command}')
        self._ser.write(command)

        if reply_fmt is not None:
            response_size = struct.calcsize(reply_fmt)
            response = self._ser.read(response_size + 4)
            if self.debug:
                responsehex = ' '.join(f'{c:02x}' for c in response)
                print(f'{responsehex:>50} ¦ {response}')

            if not response:
                raise RuntimeError('Expected response not received')

            data, crc, newline = struct.unpack(f'<{response_size}sH2s', response)
            if crc != crc_16(data) or newline != b'\r\n':
                raise RuntimeError('Response CRC not correct')

            return struct.unpack(reply_fmt, data)

    def log_metadata(self) -> dict[str, Any]:
        return {
            'name': self.uid,
            'serial_number': self.serial_number,
            'mode': self.mode,
            'temperature_c': self.temperature_c,
        }

    def close(self) -> None:
        self._ser.close()
