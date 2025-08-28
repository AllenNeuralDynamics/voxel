from abc import abstractmethod

from voxel.devices.device import VoxelDevice, VoxelDeviceType
from voxel.utils.descriptors.deliminated import deliminated_float


class VoxelFlipMount(VoxelDevice):
    """Base class for Voxel flip mounts.

    :param name: Name of the flip mount
    :type name: str
    """

    def __init__(self, name: str) -> None:
        super().__init__(device_type=VoxelDeviceType.FLIP_MOUNT, uid=name)

    @property
    @abstractmethod
    def position(self) -> str:
        """Position of the flip mount.

        :return: Name of the current position
        :rtype: str
        """

    @position.setter
    @abstractmethod
    def position(self, position_name: str) -> None:
        """Set the flip mount to a specific position.

        :param position_name: Name of the position to move to
        """

    @abstractmethod
    def toggle(self, *, wait: bool = False) -> None:
        """Toggle the flip mount position.

        :param wait: Wait for the flip mount to finish flipping. Default: False
        :type wait: bool
        """

    @abstractmethod
    def wait(self) -> None:
        """Wait for the flip mount to finish flipping."""

    @deliminated_float()
    @abstractmethod
    def flip_time_ms(self) -> float:
        """Time it takes to flip the mount in milliseconds.

        :return: Time in milliseconds
        :rtype: float
        """

    @flip_time_ms.setter
    @abstractmethod
    def flip_time_ms(self, time_ms: float) -> None:
        """Set the time it takes to flip the mount in milliseconds.

        :param time_ms: Time in milliseconds
        :type time_ms: float
        """
