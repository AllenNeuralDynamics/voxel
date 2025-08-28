from abc import abstractmethod

from voxel.devices.device import VoxelDevice, VoxelDeviceType


class VoxelPowerMeter(VoxelDevice):
    """Abstract base class for a voxel power meter."""

    def __init__(self, name: str) -> None:
        super().__init__(device_type=VoxelDeviceType.POWER_METER, uid=name)

    @property
    @abstractmethod
    def power_mw(self) -> float:
        """The power in milliwatts."""

    @property
    @abstractmethod
    def wavelength_nm(self) -> float:
        """The wavelength in nanometers."""

    @wavelength_nm.setter
    @abstractmethod
    def wavelength_nm(self, wavelength: float) -> None:
        """Set the wavelength in nanometers.

        Args:
            wavelength (float): The new wavelength in nanometers.
        """
