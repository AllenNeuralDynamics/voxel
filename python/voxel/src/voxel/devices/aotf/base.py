from abc import abstractmethod

from voxel.devices.device import VoxelDevice, VoxelDeviceType


class VoxelAOTF(VoxelDevice):
    def __init__(self, uid: str) -> None:
        super().__init__(device_type=VoxelDeviceType.AOTF, uid=uid)

    @abstractmethod
    def enable(self) -> None:
        pass

    @abstractmethod
    def disable(self) -> None:
        pass

    @property
    @abstractmethod
    def frequency_hz(self) -> float:
        pass

    @frequency_hz.setter
    @abstractmethod
    def frequency_hz(self, frequency_hz: float) -> None:
        pass

    @property
    @abstractmethod
    def power_dbm(self) -> float:
        pass

    @power_dbm.setter
    @abstractmethod
    def power_dbm(self, power_dbm: float) -> None:
        pass

    @abstractmethod
    def set_power_dbm(self, channel: int, power_dbm: dict) -> None:
        pass

    @property
    @abstractmethod
    def blanking_mode(self) -> str:
        pass

    @blanking_mode.setter
    @abstractmethod
    def blanking_mode(self, mode: str) -> None:
        pass

    @property
    @abstractmethod
    def input_mode(self) -> str:
        pass

    @input_mode.setter
    @abstractmethod
    def input_mode(self, mode: str) -> None:
        pass
