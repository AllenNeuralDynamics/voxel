from abc import abstractmethod

from ..base import VoxelDevice


class BaseFlipMount(VoxelDevice):
    def __init__(self, id: str):
        super().__init__(id)

    @property
    @abstractmethod
    def position(self) -> str | None:
        """Position of the flip mount."""
        pass

    @position.setter
    @abstractmethod
    def position(self, position_name: str, wait=False):
        """Set the flip mount to a specific position"""
        pass

    @abstractmethod
    def toggle(self):
        """Toggle the flip mount position"""
        pass

    @abstractmethod
    def wait(self):
        """Wait for the flip mount to finish flipping."""
        pass

    @property
    @abstractmethod
    def flip_time_ms(self) -> int:
        """Time it takes to flip the mount in milliseconds."""
        pass

    @flip_time_ms.setter
    @abstractmethod
    def flip_time_ms(self, time_ms: int):
        pass


# Path: voxel/devices/flip_mount/thorlabs_mff101.py
