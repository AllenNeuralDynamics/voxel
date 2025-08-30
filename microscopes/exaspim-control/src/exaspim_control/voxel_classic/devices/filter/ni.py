from exaspim_control.voxel_classic.devices.filter.base import BaseFilter
from exaspim_control.voxel_classic.devices.filterwheel.ni import DAQFilterWheel
from voxel.utils.log import VoxelLogging


class Filter(BaseFilter):
    """Filter class for handling ASI filter devices."""

    def __init__(self, wheel: DAQFilterWheel, id: str) -> None:
        """Initialize the Filter object.

        :param wheel: Filter wheel object
        :type wheel: FilterWheel
        :param id: Filter ID
        :type id: str
        """
        self.log = VoxelLogging.get_logger(obj=self)
        self.id = id
        self.wheel = wheel

    def enable(self) -> None:
        """Enable the filter device."""
        self.wheel.filter = self.id

    def close(self) -> None:
        """Close the filter device."""
