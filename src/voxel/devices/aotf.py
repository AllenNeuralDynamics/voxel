from abc import abstractmethod

from .base import VoxelDevice, VoxelDeviceType


class VoxelAOTF(VoxelDevice):
    def __init__(self, name) -> None:
        super().__init__(device_type=VoxelDeviceType.AOTF, name=name)

    @abstractmethod
    def enable_all(self) -> None:
        pass

    @abstractmethod
    def disable_all(self) -> None:
        pass

    @property
    @abstractmethod
    def frequency_hz(self) -> None:
        pass

    @abstractmethod
    def set_frequency_hz(self, channel: int, frequency_hz: dict) -> None:
        pass

    @property
    @abstractmethod
    def power_dbm(self):
        pass

    @abstractmethod
    def set_power_dbm(self, channel: int, power_dbm: dict):
        pass

    @property
    @abstractmethod
    def blanking_mode(self):
        pass

    @blanking_mode.setter
    @abstractmethod
    def blanking_mode(self, mode: str):
        pass

    @property
    @abstractmethod
    def input_mode(self):
        pass

    @input_mode.setter
    @abstractmethod
    def input_mode(self, modes: dict):
        pass
