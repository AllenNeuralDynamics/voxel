import logging
import struct
import serial
from voxel.devices.tunable_lens.base import BaseTunableLens

# constants for Optotune EL-E-4i controller

MODES = {
    "external": ['MwDA', '>xxx'],
    "internal": ['MwCA', '>xxxBhh'],
}

def crc_16(s):
    crc = 0x0000
    for c in s:
        crc = crc ^ c
        for i in range(0, 8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) > 0 else crc >> 1

    return crc

class TunableLens(BaseTunableLens):

    def __init__(self, port: str):

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        # (!!) hardcode debug to false
        self.debug = False
        self.tunable_lens = serial.Serial(port=port, baudrate=115200, timeout=1)
        self.tunable_lens.flush()
        # set id to serial number of lens
        self.id = self.send_command('X', '>x8s')[0].decode('ascii')

    @property
    def mode(self):
        """Get the tunable lens control mode."""
        mode = self.send_command('MMA', '>xxxB')[0]

        if mode == 1:
            return 'internal'
        if mode == 5:
            return 'external'

    @mode.setter
    def mode(self, mode: str):
        """Set the tunable lens control mode."""

        valid = list(MODES.keys())
        if mode not in valid:
            raise ValueError("mode must be one of %r." % valid)
        mode_list = MODES[mode]
        self.send_command(mode_list[0], mode_list[1])

    @property
    def signal_temperature_c(self):
        """Get the temperature in deg C."""
        state = {}
        state['Temperature [C]'] = self.send_command(b'TCA', '>xxxh')[0] * 0.0625
        return state

    def send_command(self, command, reply_fmt=None):
        if type(command) is not bytes:
            command = bytes(command, encoding='ascii')
        command = command + struct.pack('<H', crc_16(command))
        if self.debug:
            commandhex = ' '.join('{:02x}'.format(c) for c in command)
            print('{:<50} ¦ {}'.format(commandhex, command))
        self.tunable_lens.write(command)

        if reply_fmt is not None:
            response_size = struct.calcsize(reply_fmt)
            response = self.tunable_lens.read(response_size+4)
            if self.debug:
                responsehex = ' '.join('{:02x}'.format(c) for c in response)
                print('{:>50} ¦ {}'.format(responsehex, response))

            if response is None:
                raise Exception('Expected response not received')

            data, crc, newline = struct.unpack('<{}sH2s'.format(response_size), response)
            if crc != crc_16(data) or newline != b'\r\n':
                raise Exception('Response CRC not correct')

            return struct.unpack(reply_fmt, data)

    def close(self):
        self.tunable_lens.close()