from abc import abstractmethod

from .base import VoxelDevice, VoxelDeviceType


class VoxelRotationAxis(VoxelDevice):
    """Abstract base class for a voxel rotation axis."""

    def __init__(self, name: str) -> None:
        super().__init__(device_type=VoxelDeviceType.ROTATION_AXIS, name=name)

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
    def position_deg(self, value: float) -> None:
        """Set the position of the rotation axis in degrees.
        :param value: The new position in degrees
        :type value: float
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
    def speed_deg_s(self, value: float) -> None:
        """Set the speed of the rotation axis in degrees per second.
        :param value: The new speed in degrees per second
        :type value: float
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
    def wait_until_stopped(self, timeout: float | None = None, check_interval: float = 0.1) -> None:
        """Wait until the rotation axis has stopped moving.
        :param timeout: Maximum time to wait for the rotation axis to stop moving
        :param check_interval: Time interval between checks
        :type timeout: float
        :type check_interval: float
        """
        pass
