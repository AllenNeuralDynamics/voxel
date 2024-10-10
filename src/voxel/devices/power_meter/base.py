from ..base import VoxelDevice

from abc import abstractmethod


class BasePowerMeter(VoxelDevice):
    """
    Abstract base class for a voxel power meter.
    """

    def __init__(self, id: str) -> None:
        super().__init__(id)

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
