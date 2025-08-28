from abc import abstractmethod
from enum import StrEnum
from typing import TypedDict

from voxel.devices.device import VoxelDevice, VoxelDeviceType


class ETLControlMode(StrEnum):
    """Tunable lens control modes."""

    INTERNAL = 'internal'
    EXTERNAL = 'external'
    UNKNOWN = 'unknown'


class ETLMetadata(TypedDict):
    name: str
    mode: ETLControlMode
    temperature_c: float | None


class VoxelTunableLens(VoxelDevice):
    def __init__(self, name: str) -> None:
        super().__init__(device_type=VoxelDeviceType.TUNABLE_LENS, uid=name)

    @property
    @abstractmethod
    def mode(self) -> ETLControlMode:
        """Get the tunable lens control mode."""

    @mode.setter
    @abstractmethod
    def mode(self, mode: ETLControlMode) -> None:
        """Set the tunable lens control mode.

        :param mode: one of "internal" or "external".
        :type mode: str.
        """

    @property
    @abstractmethod
    def temperature_c(self) -> float | None:
        """Get the temperature in deg C."""
