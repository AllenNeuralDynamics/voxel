from typing import Optional
from ..base import VoxelDevice

from abc import abstractmethod


class BaseRotationAxis(VoxelDevice):
    """Abstract base class for a voxel rotation axis."""
    def __init__(self, id: str) -> None:
        super().__init__(id)

    @property
    @abstractmethod
    def position_deg(self) -> float:
        """Return the current position of the rotation axis in degrees.
        :return: The current position in degrees
        :rtype: float
        """
        pass

    @position_deg.setter
    @abstractmethod
    def position_deg(self, position: float) -> None:
        """Set the position of the rotation axis in degrees.
        :param position: The new position in degrees
        :type position: float
        """
        pass

    @property
    @abstractmethod
    def speed_deg_s(self) -> float:
        """Return the speed of the rotation axis in degrees per second.
        :return: The speed in degrees per second
        :rtype: float
        """
        pass

    @speed_deg_s.setter
    @abstractmethod
    def speed_deg_s(self, speed: float) -> None:
        """Set the speed of the rotation axis in degrees per second.
        :param speed: The new speed in degrees per second
        :type speed: float
        """
        pass

    @property
    @abstractmethod
    def is_moving(self) -> bool:
        """Check if the rotation axis is moving.
        :return: True if moving, False otherwise
        :rtype: bool
        """
        pass

    @abstractmethod
    def wait_until_stopped(self, timeout: Optional[float]= None, check_interval: float = 0.1) -> None:
        """Wait until the rotation axis has stopped moving.
        :param timeout: Maximum time to wait for the rotation axis to stop moving
        :param check_interval: Time interval between checks
        :type timeout: float
        :type check_interval: float
        """
        pass
