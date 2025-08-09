import time

import serial

from voxel.devices.interfaces.chiller import VoxelChiller

from . import SMCCommand, SMCControl

BAUD_RATE = 1200
WAIT_TIME = 0.1  # in seconds
SER_TIMEOUT = 1  # in seconds


class SMCChiller(VoxelChiller):
    def __init__(self, conn: str, name: str = "", unit=None, persist=True):
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

        if not self._validate_connection():
            raise Exception("Failed to validate connection with the SMC Chiller.")

    def _validate_connection(self):
        try:
            response = self._read_value(SMCCommand.READ_INTERNAL_SENSOR)
            return bool(response)
        except Exception as e:
            print(f"Validation error: {e}")
            return False

    def _complete_packet(self, packet):
        if self.unit is not None:
            unit_code = ord("0") + self.unit
            packet = [SMCControl.SOH.value, unit_code] + packet
        checksum = sum(packet) & 0xFF
        return packet + [checksum, SMCControl.CR.value]

    def _send_SMCcommand(self, SMCcommand, data):
        packet = [SMCControl.STX.value, SMCcommand.value] + data + [SMCControl.ETX.value]
        full_SMCcommand = self._complete_packet(packet)
        self.ser.write(bytearray(full_SMCcommand))
        time.sleep(0.1)
        response = self.ser.read_all()
        return response and response[0] == SMCControl.ACK.value

    def _read_value(self, SMCcommand):
        packet = [SMCControl.ENQ.value, SMCcommand.value]
        full_SMCcommand = self._complete_packet(packet)
        self.ser.write(bytearray(full_SMCcommand))
        time.sleep(0.1)
        response = self.ser.read_all()

        if response:
            # Send ACK after receiving the response
            ack_packet = [SMCControl.ACK.value, SMCControl.CR.value]
            self.ser.write(bytearray(ack_packet))

        return response

    def _parse_temperature(self, response):
        temp_str = response.decode().strip()
        return float(temp_str) / 10

    @property
    def temperature_c(self) -> float:
        response = self._read_value(SMCCommand.READ_INTERNAL_SENSOR)
        return self._parse_temperature(response)

    @temperature_c.setter
    def temperature_c(self, value: float) -> None:
        SMCcommand = SMCCommand.SET_TEMPERATURE_FRAM if self.persist else SMCCommand.SET_TEMPERATURE_NO_FRAM
        temp_str = f"{int(value * 10):04d}"
        data = [ord(c) for c in temp_str]
        self._send_SMCcommand(SMCcommand, data)

    @property
    def external_temperature_c(self):
        response = self._read_value(SMCCommand.READ_EXTERNAL_SENSOR)
        return self._parse_temperature(response)

    @property
    def alarm_status(self) -> str | None:
        response = self._read_value(SMCCommand.READ_ALARM_STATUS)
        return response.decode().strip() if response else None

    def set_offset(self, offset):
        SMCcommand = SMCCommand.SET_OFFSET_FRAM if self.persist else SMCCommand.SET_OFFSET_NO_FRAM
        offset_str = f"{int(offset * 100):04d}"
        data = [ord(c) for c in offset_str]
        self._send_SMCcommand(SMCcommand, data)

    def close(self):
        self.ser.close()


# Example usage
if __name__ == "__main__":
    chiller = SMCChiller("test-chiller", "COM1")

    print("Internal Sensor Temperature:", chiller.temperature_c)

    print("External Sensor Temperature:", chiller.external_temperature_c)

    print("Alarm Status:", chiller.alarm_status)

    chiller.temperature_c = 25.0
    print("Temperature set to 25.0°C and persisted.")

    chiller.persist = False
    chiller.temperature_c = 25.0
    print("Temperature set to 25.0°C without persisting.")

    chiller.persist = True
    chiller.set_offset(2.5)
    print("Offset set to 2.5°C and persisted.")
    chiller.close()
