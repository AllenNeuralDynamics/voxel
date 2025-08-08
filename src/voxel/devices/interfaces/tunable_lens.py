from abc import abstractmethod
from enum import StrEnum

from ..base import VoxelDevice, VoxelDeviceType


class ETLControlMode(StrEnum):
    """Tunable lens control modes."""

    INTERNAL = "internal"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class VoxelTunableLens(VoxelDevice):
    def __init__(self, name: str) -> None:
        super().__init__(device_type=VoxelDeviceType.TUNABLE_LENS, uid=name)

    @property
    @abstractmethod
    def mode(self) -> ETLControlMode:
        """Get the tunable lens control mode."""
        pass

    @mode.setter
    @abstractmethod
    def mode(self, mode: ETLControlMode) -> None:
        """Set the tunable lens control mode.
        :param mode: one of "internal" or "external".
        :type mode: str
        """
        pass

    @property
    @abstractmethod
    def temperature_c(self) -> float:
        """Get the temperature in deg C."""
        pass
