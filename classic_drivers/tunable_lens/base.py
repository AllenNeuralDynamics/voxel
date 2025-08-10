from abc import abstractmethod

from voxel_classic.devices.base import VoxelDevice


class BaseTunableLens(VoxelDevice):
    """
    Base class for tunable lens devices.
    """

    @property
    @abstractmethod
    def mode(self) -> str:
        """
        Get the mode of the tunable lens.

        :return: Mode of the tunable lens
        :rtype: str
        """
        pass

    @mode.setter
    @abstractmethod
    def mode(self, mode: str) -> None:
        """
        Set the mode of the tunable lens.

        :param mode: Mode of the tunable lens
        :type mode: str
        """
        pass

    @property
    @abstractmethod
    def temperature_c(self) -> float:
        """
        Get the temperature of the tunable lens in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        pass

    @abstractmethod
    def log_metadata(self) -> None:
        """
        Log metadata for the tunable lens.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the tunable lens device.
        """
        pass
