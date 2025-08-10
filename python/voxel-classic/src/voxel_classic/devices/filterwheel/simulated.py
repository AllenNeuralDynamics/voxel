import time

from voxel.utils.log import VoxelLogging
from voxel_classic.devices.filterwheel.base import BaseFilterWheel

SWITCH_TIME_S = 0.1  # estimated timing


class SimulatedFilterWheel(BaseFilterWheel):
    """
    FilterWheel class for handling simulated filter wheel devices.
    """

    def __init__(self, id: str, filters: dict[str, int]) -> None:
        """
        Initialize the FilterWheel object.

        :param id: Filter wheel ID
        :type id: str
        :param filters: Dictionary of filters
        :type filters: dict
        """
        self.log = VoxelLogging.get_logger(object=self)
        self.id = id
        self._filters = filters
        # force homing of the wheel to first position
        self.filter = next(iter(filters))

    @property
    def filters(self) -> dict[str, int]:
        """
        Get the list of available filters.
        """
        return self._filters

    @property
    def filter(self) -> str:
        """
        Get the current filter.

        :return: Current filter name
        :rtype: str
        """
        return self._filter

    @filter.setter
    def filter(self, filter_name: str) -> None:
        """
        Set the current filter.

        :param filter_name: Filter name
        :type filter_name: str
        """
        self.log.info(f"setting filter to {filter_name}")
        if filter_name not in self._filters:
            raise ValueError(f"Filter {filter_name} not in filter list: {self._filters}")
        self._filter = filter_name
        time.sleep(SWITCH_TIME_S)

    def close(self):
        """
        Close the filter wheel device.
        """
        pass
