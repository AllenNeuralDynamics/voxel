import logging

from aaopto_aotf import MPDS
from aaopto_aotf.device_codes import *

from voxel.devices.utils.singleton import Singleton

BLANKING_MODES = {
    "external": BlankingMode.EXTERNAL,
    "internal": BlankingMode.INTERNAL,
}

INPUT_MODES = {
    "external": InputMode.EXTERNAL,
    "internal": InputMode.INTERNAL,
}


# singleton wrapper around MPDS
class MPDSSingleton(MPDS, metaclass=Singleton):
    def __init__(self, com_port):
        super(MPDSSingleton, self).__init__(com_port)


class AOTF(BaseAOTF):

    def __init__(self, port: str):

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.aotf = MPDSSingleton(com_port=port)
        self.id = self.aotf.get_product_id()

    # def enable_all(self):
    #      for channel in range(self.aotf.num_channels):
    #         self.enable_channel(channel)

    # def disable_all(self):
    #      for channel in range(self.aotf.num_channels):
    #         self.disable_channel(channel)

    @property
    def frequency_hz(self):
        frequency_hz = dict()
        for channel in range(self.aotf.num_channels):
            frequency_hz[channel] = self.aotf.get_frequency(channel)
        return frequency_hz

    @frequency_hz.setter
    def frequency_hz(self, channel: int, frequency_hz: dict):
        for key in frequency_hz:
            self.aotf.set_frequency(channel=channel, frequency=frequency_hz[key])
        self.aotf.save_profile()

    @property
    def power_dbm(self):
        power_dbm = dict()
        for channel in range(self.aotf.num_channels):
            power_dbm[channel] = self.aotf.get_power_dbm(channel)
        return power_dbm

    @power_dbm.setter
    def power_dbm(self, channel: int, power_dbm: dict):
        for key in power_dbm:
            self.aotf.set_frequency(channel=channel, frequency=power_dbm[key])
        self.aotf.save_profile()

    @property
    def blanking_mode(self):
        mode = self.aotf.get_blanking_mode()
        converted_mode = next(key for key, enum in BLANKING_MODES.items() if enum.value == mode)
        return converted_mode

    @blanking_mode.setter
    def blanking_mode(self, mode: str):
        valid = list(BLANKING_MODES.keys())
        if mode not in valid:
            raise ValueError("blanking mode must be one of %r." % valid)
        self.aotf.set_blanking_mode(BLANKING_MODES[mode])

    # @property
    # def input_mode(self):
    #     modes = dict()
    #     for channel in range(self.aotf.num_channels):
    #         modes[channel] = self.aotf.get_channel_input_mode(channel)
    #     converted_mode = next(key for key, enum in INPUT_MODES.items() if enum.value == mode)
    #     return converted_mode

    # @input_mode.setter
    # def input_mode(self, modes: dict):
    #     valid = list(INPUT_MODES.keys())
    #     for key in modes:
    #         if modes[key] not in valid:
    #             raise ValueError("input mode must be one of %r." % valid)

    #     for key in modes:
    #         self.aotf.set_channel_input_mode(channel=key, mode=INPUT_MODES[mode])
