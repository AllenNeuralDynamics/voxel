from abc import abstractmethod

from .base import VoxelDevice, VoxelDeviceType


class VoxelAOTF(VoxelDevice):
    def __init__(self, name) -> None:
        super().__init__(device_type=VoxelDeviceType.AOTF, name=name)

    @abstractmethod
    def enable(self) -> None:
        pass

    @abstractmethod
    def disable(self) -> None:
        pass

    @property
    @abstractmethod
    def frequency_hz(self) -> None:
        pass

    @frequency_hz.setter
    @abstractmethod
    def frequency_hz(self, frequency_hz: int) -> None:
        pass

    @property
    @abstractmethod
    def power_dbm(self):
        pass

    @power_dbm.setter
    @abstractmethod
    def power_dbm(self, power_dbm: float):
        pass

    @abstractmethod
    def set_power_dbm(self, channel: int, power_dbm: dict):
        pass

    @property
    @abstractmethod
    def blanking_mode(self) -> str:
        pass

    @blanking_mode.setter
    @abstractmethod
    def blanking_mode(self, mode: str):
        pass

    @property
    @abstractmethod
    def input_mode(self) -> str:
        pass

    @input_mode.setter
    @abstractmethod
    def input_mode(self, mode: str):
        pass
