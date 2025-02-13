import logging

from aaopto_aotf import MPDS
from aaopto_aotf.device_codes import *

from voxel.devices.aotf.base import BaseAOTF
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
    """
    Singleton wrapper around the MPDS class.
    """

    def __init__(self, com_port: str) -> None:
        """
        Initialize the MPDSSingleton class.

        :param com_port: The COM port for the AOTF device.
        :type com_port: str
        """
        super(MPDSSingleton, self).__init__(com_port)


class AAOptoAOTF(BaseAOTF):
    """
    Class for controlling an Acousto-Optic Tunable Filter (AOTF).
    """

    def __init__(self, port: str) -> None:
        """
        Initialize the AOTF class.

        :param port: The COM port for the AOTF device.
        :type port: str
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.aotf = MPDSSingleton(com_port=port)
        self.id = self.aotf.get_product_id()

    def enable_all(self) -> None:
        """
        Enable all channels of the AOTF.
        """
        for channel in range(self.aotf.num_channels):
            self.enable_channel(channel)

    def disable_all(self) -> None:
        """
        Disable all channels of the AOTF.
        """
        for channel in range(self.aotf.num_channels):
            self.disable_channel(channel)

    @property
    def frequency_hz(self) -> dict:
        """
        Get the frequency in Hz for each channel.

        :return: A dictionary with channel numbers as keys and frequencies as values.
        :rtype: dict
        """
        frequency_hz = dict()
        for channel in range(self.aotf.num_channels):
            frequency_hz[channel] = self.aotf.get_frequency(channel)
        return frequency_hz

    @frequency_hz.setter
    def frequency_hz(self, frequency_hz: dict) -> None:
        """
        Set the frequency in Hz for a specific channel.

        :param frequency_hz: A dictionary with channel numbers as keys and frequencies as values.
        :type frequency_hz: dict
        """
        for channel, freq in frequency_hz.items():
            self.aotf.set_frequency(channel=channel, frequency=freq)
        self.aotf.save_profile()

    @property
    def power_dbm(self) -> dict:
        """
        Get the power in dBm for each channel.

        :return: A dictionary with channel numbers as keys and power levels as values.
        :rtype: dict
        """
        power_dbm = dict()
        for channel in range(self.aotf.num_channels):
            power_dbm[channel] = self.aotf.get_power_dbm(channel)
        return power_dbm

    @power_dbm.setter
    def power_dbm(self, power_dbm: dict) -> None:
        """
        Set the power in dBm for a specific channel.

        :param power_dbm: A dictionary with channel numbers as keys and power levels as values.
        :type power_dbm: dict
        """
        for channel, power in power_dbm.items():
            self.aotf.set_power_dbm(channel=channel, power=power)
        self.aotf.save_profile()

    @property
    def blanking_mode(self) -> str:
        """
        Get the current blanking mode.

        :return: The blanking mode.
        :rtype: str
        """
        mode = self.aotf.get_blanking_mode()
        converted_mode = next(key for key, enum in BLANKING_MODES.items() if enum.value == mode)
        return converted_mode

    @blanking_mode.setter
    def blanking_mode(self, mode: str) -> None:
        """
        Set the blanking mode.

        :param mode: The blanking mode to set.
        :type mode: str
        :raises ValueError: If the mode is not valid.
        """
        valid = list(BLANKING_MODES.keys())
        if mode not in valid:
            raise ValueError("blanking mode must be one of %r." % valid)
        self.aotf.set_blanking_mode(BLANKING_MODES[mode])

    @property
    def input_mode(self) -> dict:
        """
        Get the current input mode for each channel.

        :return: A dictionary with channel numbers as keys and input modes as values.
        :rtype: dict
        """
        modes = dict()
        for channel in range(self.aotf.num_channels):
            modes[channel] = self.aotf.get_channel_input_mode(channel)
        return modes

    @input_mode.setter
    def input_mode(self, modes: dict) -> None:
        """
        Set the input mode for each channel.

        :param modes: A dictionary with channel numbers as keys and input modes as values.
        :type modes: dict
        :raises ValueError: If the mode is not valid.
        """
        valid = list(INPUT_MODES.keys())
        for key in modes:
            if modes[key] not in valid:
                raise ValueError("input mode must be one of %r." % valid)

        for key, mode in modes.items():
            self.aotf.set_channel_input_mode(channel=key, mode=INPUT_MODES[mode])
