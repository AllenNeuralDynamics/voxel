from abc import abstractmethod
from voxel.devices.base import VoxelDevice, VoxelDeviceType
from voxel.utils.descriptors.enumerated import enumerated_string


class VoxelFilterWheel(VoxelDevice):
    def __init__(self, name: str) -> None:
        super().__init__(name=name, device_type=VoxelDeviceType.FILTER_WHEEL)

    @property
    @abstractmethod
    def filters(self) -> dict[str, int]:
        """Return a dictionary of filter names and their corresponding positions."""
        pass

    @enumerated_string(options=lambda self: self.filters.keys())
    @abstractmethod
    def current_filter(self) -> str:
        """Return the name of the currently active filter, or None if no filter is active."""
        pass

    @current_filter.setter
    def current_filter(self, filter_name: str) -> None:
        """Set the current filter to the specified filter name."""
        pass
