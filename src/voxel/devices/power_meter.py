from abc import abstractmethod

from .base import VoxelDevice, VoxelDeviceType


class VoxelPowerMeter(VoxelDevice):
    """
    Abstract base class for a voxel power meter.
    """

    def __init__(self, name: str) -> None:
        super().__init__(device_type=VoxelDeviceType.POWER_METER, name=name)

    @property
    @abstractmethod
    def power_mw(self) -> float:
        """
        Returns:
        float: The power in milliwatts.
        """
        pass

    @property
    @abstractmethod
    def wavelength_nm(self) -> float:
        """
        Returns:
        int: The wavelength in nanometers.
        """
        pass

    @wavelength_nm.setter
    @abstractmethod
    def wavelength_nm(self, wavelength: float):
        """
        Parameters:
        wavelength (int): The new wavelength in nanometers.
        """
        pass
