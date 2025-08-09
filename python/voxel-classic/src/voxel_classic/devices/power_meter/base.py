from abc import abstractmethod

from voxel_classic.devices.base import VoxelDevice


class BasePowerMeter(VoxelDevice):
    """
    Base class for power meter devices.
    """

    def __init__(self, id: str) -> None:
        """
        Initialize the BasePowerMeter object.

        :param id: Power meter ID
        :type id: str
        """
        super().__init__(id)

    @property
    @abstractmethod
    def power_mw(self) -> float:
        """
        Get the power in milliwatts.

        :return: Power in milliwatts
        :rtype: float
        """
        pass

    @property
    @abstractmethod
    def wavelength_nm(self) -> float:
        """
        Get the wavelength in nanometers.

        :return: Wavelength in nanometers
        :rtype: float
        """
        pass

    @wavelength_nm.setter
    @abstractmethod
    def wavelength_nm(self, wavelength: float) -> None:
        """
        Set the wavelength in nanometers.

        :param wavelength: Wavelength in nanometers
        :type wavelength: float
        """
        pass
