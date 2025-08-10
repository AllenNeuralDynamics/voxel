from abc import abstractmethod
from typing import Dict

from voxel_classic.devices.base import VoxelDevice


class BaseAOTF(VoxelDevice):
    """
    Base class for Acousto-Optic Tunable Filter (AOTF) devices.
    """

    @abstractmethod
    def enable_all(self) -> None:
        """
        Enable all channels of the AOTF.
        """
        pass

    @abstractmethod
    def disable_all(self) -> None:
        """
        Disable all channels of the AOTF.
        """
        pass

    @property
    @abstractmethod
    def frequency_hz(self) -> Dict[int, float]:
        """
        Get the frequency in Hz for the AOTF.

        :return: The frequency in Hz.
        :rtype: dict
        """
        pass

    @frequency_hz.setter
    @abstractmethod
    def frequency_hz(self, frequency_hz: Dict[int, float]) -> None:
        """
        Set the frequency in Hz for a specific channel of the AOTF.

        :param frequency_hz: The frequency in Hz.
        :type frequency_hz: dict
        """
        pass

    @property
    @abstractmethod
    def power_dbm(self) -> Dict[int, float]:
        """
        Get the power in dBm for the AOTF.

        :return: The power in dBm.
        :rtype: dict
        """
        pass

    @power_dbm.setter
    @abstractmethod
    def power_dbm(self, power_dbm: Dict[int, float]) -> None:
        """
        Set the power in dBm for a specific channel of the AOTF.

        :param power_dbm: The power in dBm.
        :type power_dbm: dict
        """
        pass

    @property
    @abstractmethod
    def blanking_mode(self) -> str:
        """
        Get the blanking mode of the AOTF.

        :return: The blanking mode.
        :rtype: str
        """
        pass

    @blanking_mode.setter
    @abstractmethod
    def blanking_mode(self, mode: str) -> None:
        """
        Set the blanking mode of the AOTF.

        :param mode: The blanking mode.
        :type mode: str
        """
        pass

    @property
    @abstractmethod
    def input_mode(self) -> Dict[int, str]:
        """
        Get the input mode of the AOTF.

        :return: The input mode.
        :rtype: dict
        """
        pass

    @input_mode.setter
    @abstractmethod
    def input_mode(self, modes: Dict[int, str]) -> None:
        """
        Set the input mode of the AOTF.

        :param modes: The input modes.
        :type modes: dict
        """
        pass
