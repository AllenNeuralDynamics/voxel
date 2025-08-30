import time

import serial
from voxel.devices.chiller import VoxelChiller
from voxel.devices.chiller.drivers.smc.codes import SMCCommand, SMCControl

BAUD_RATE = 1200
WAIT_TIME = 0.1  # in seconds
SER_TIMEOUT = 1  # in seconds


class SMCChiller(VoxelChiller):
    def __init__(self, conn: str, name: str = '', unit: int | None = None, persist: bool = True) -> None:
        super().__init__(name)
        self.port = conn
        self.baudrate = BAUD_RATE
        self.timeout = SER_TIMEOUT
        self.persist = persist
        self.unit = unit

        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=self.timeout,
        )
        try:
            res = self._read_value(SMCCommand.READ_INTERNAL_SENSOR)
            self.log.debug('Successfully read from SMC Chiller during initialization. Internal Sensor Read: %s', res)
        except Exception as e:
            raise ValueError('Failed to validate connection with the SMC Chiller.') from e

    def _complete_packet(self, packet: list[int]) -> list[int]:
        if self.unit is not None:
            unit_code = ord('0') + self.unit
            packet = [SMCControl.SOH.value, unit_code, *packet]
        checksum = sum(packet) & 0xFF
        return [*packet, checksum, SMCControl.CR.value]

    def _send_command(self, cmd: SMCCommand, data: list[int]) -> bool:
        packet = [SMCControl.STX.value, cmd.value, *data, SMCControl.ETX.value]
        full_cmd = self._complete_packet(packet)
        self.ser.write(bytearray(full_cmd))
        time.sleep(0.1)
        response = self.ser.read_all()
        return response is not None and response[0] == SMCControl.ACK.value

    def _read_value(self, cmd: SMCCommand) -> bytes | None:
        packet = [SMCControl.ENQ.value, cmd.value]
        full_cmd = self._complete_packet(packet)
        self.ser.write(bytearray(full_cmd))
        time.sleep(0.1)
        response = self.ser.read_all()

        if response:
            # Send ACK after receiving the response
            ack_packet = [SMCControl.ACK.value, SMCControl.CR.value]
            self.ser.write(bytearray(ack_packet))

        return response

    def _parse_temperature(self, response: bytes) -> float:
        temp_str = response.decode().strip()
        return float(temp_str) / 10

    @property
    def temperature_c(self) -> float | None:
        response = self._read_value(SMCCommand.READ_INTERNAL_SENSOR)
        return self._parse_temperature(response) if response else None

    @temperature_c.setter
    def temperature_c(self, value: float) -> None:
        cmd = SMCCommand.SET_TEMPERATURE_FRAM if self.persist else SMCCommand.SET_TEMPERATURE_NO_FRAM
        temp_str = f'{int(value * 10):04d}'
        data = [ord(c) for c in temp_str]
        self._send_command(cmd, data)

    @property
    def external_temperature_c(self) -> float | None:
        response = self._read_value(SMCCommand.READ_EXTERNAL_SENSOR)
        return self._parse_temperature(response) if response else None

    @property
    def alarm_status(self) -> str | None:
        response = self._read_value(SMCCommand.READ_ALARM_STATUS)
        return response.decode().strip() if response else None

    def set_offset(self, offset: float) -> None:
        cmd = SMCCommand.SET_OFFSET_FRAM if self.persist else SMCCommand.SET_OFFSET_NO_FRAM
        offset_str = f'{int(offset * 100):04d}'
        data = [ord(c) for c in offset_str]
        self._send_command(cmd, data)

    def close(self) -> None:
        self.ser.close()


# Example usage
if __name__ == '__main__':
    chiller = SMCChiller('test-chiller', 'COM1')

    print('Internal Sensor Temperature:', chiller.temperature_c)

    print('External Sensor Temperature:', chiller.external_temperature_c)

    print('Alarm Status:', chiller.alarm_status)

    chiller.temperature_c = 25.0
    print('Temperature set to 25.0°C and persisted.')

    chiller.persist = False
    chiller.temperature_c = 25.0
    print('Temperature set to 25.0°C without persisting.')

    chiller.persist = True
    chiller.set_offset(2.5)
    print('Offset set to 2.5°C and persisted.')
    chiller.close()
