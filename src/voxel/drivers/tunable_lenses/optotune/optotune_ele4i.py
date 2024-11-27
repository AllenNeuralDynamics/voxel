import struct

import serial

from voxel.instrument.devices.tunable_lens import VoxelTunableLens, TunableLensControlMode

# constants for Optotune EL-E-4i controller

MODES = {
    TunableLensControlMode.EXTERNAL: ["MwDA", ">xxx"],
    TunableLensControlMode.INTERNAL: ["MwCA", ">xxxBhh"],
}


def crc_16(s):
    crc = 0x0000
    for c in s:
        crc = crc ^ c
        for i in range(0, 8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) > 0 else crc >> 1

    return crc


class OptotuneELE4ITunableLens(VoxelTunableLens):
    def __init__(self, name: str, port: str):
        super().__init__(name)

        self.debug = False

        self._ser = serial.Serial(port=port, baudrate=115200, timeout=1)
        self._ser.flush()
        res = self._send_command("X", ">x8s")
        if res:
            try:
                self.serial_number = res[0].decode("ascii")
            except IndexError:
                self.log.error(f"Error reading serial number: {res}")

    @property
    def mode(self) -> TunableLensControlMode:
        """Get the tunable lens control mode."""
        res = self._send_command("MMA", ">xxxB")
        if res is None:
            self.log.error("Error reading mode")
        else:
            try:
                mode = None
                if res[0] == 1:
                    mode = TunableLensControlMode.INTERNAL
                if res[0] == 5:
                    mode = TunableLensControlMode.EXTERNAL
                self.log.debug(f"Mode: {mode}")
                return mode
            except IndexError:
                self.log.error(f"Error reading mode: {res}")

    @mode.setter
    def mode(self, mode: TunableLensControlMode):
        """Set the tunable lens control mode."""
        mode_list = MODES[mode]
        self._send_command(mode_list[0], mode_list[1])

    @property
    def temperature_c(self):
        """Get the temperature in deg C."""
        temp_res = self._send_command("TCA", ">xxxh")
        return {"Temperature [C]": temp_res[0] * 0.0625 if temp_res else None}

    def _send_command(self, command, reply_fmt=None):
        if type(command) is not bytes:
            command = bytes(command, encoding="ascii")
        command += struct.pack("<H", crc_16(command))
        if self.debug:
            commandhex = " ".join("{:02x}".format(c) for c in command)
            print("{:<50} ¦ {}".format(commandhex, command))
        self._ser.write(command)

        if reply_fmt is not None:
            response_size = struct.calcsize(reply_fmt)
            response = self._ser.read(response_size + 4)
            if self.debug:
                responsehex = " ".join("{:02x}".format(c) for c in response)
                print("{:>50} ¦ {}".format(responsehex, response))

            if not response:
                raise Exception("Expected response not received")

            data, crc, newline = struct.unpack("<{}sH2s".format(response_size), response)
            if crc != crc_16(data) or newline != b"\r\n":
                raise Exception("Response CRC not correct")

            return struct.unpack(reply_fmt, data)

    def log_metadata(self):
        return {
            "name": self.name,
            "serial_number": self.serial_number,
            "mode": self.mode,
            "temperature_c": self.temperature_c,
        }

    def close(self):
        self._ser.close()
