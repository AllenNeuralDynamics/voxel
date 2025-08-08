from abc import abstractmethod

from voxel_classic.devices.base import VoxelDevice


class BaseRotationMount(VoxelDevice):
    """
    Base class for rotation mount devices.
    """

    @property
    @abstractmethod
    def position_deg(self) -> float:
        """
        Get the current position of the rotation mount in degrees.

        :return: Current position in degrees
        :rtype: float
        """
        pass

    @abstractmethod
    @position_deg.setter
    def position_deg(self, value: float) -> None:
        """
        Set the position of the rotation mount in degrees.

        :param value: Position in degrees
        :type value: float
        :raises ValueError: If the position is out of range
        """
        pass

    @property
    @abstractmethod
    def speed_deg_s(self) -> float:
        """
        Get the speed of the rotation mount in degrees per second.

        :return: Speed in degrees per second
        :rtype: float
        """
        pass

    @speed_deg_s.setter
    def speed_deg_s(self, value: float) -> None:
        """
        Set the speed of the rotation mount in degrees per second.

        :param value: Speed in degrees per second
        :type value: float
        :raises ValueError: If the speed is out of range
        """
        pass

    def close(self) -> None:
        """
        Close the rotation mount connection.
        """
        pass
