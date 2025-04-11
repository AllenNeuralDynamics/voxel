import logging
import time
from typing import Dict

from voxel.devices.filterwheel.base import BaseFilterWheel

FILTERS = list()

SWITCH_TIME_S = 0.1  # estimated timing


class SimulatedFilterWheel(BaseFilterWheel):
    """
    FilterWheel class for handling simulated filter wheel devices.
    """

    def __init__(self, id: str, filters: Dict[str, int]) -> None:
        """
        Initialize the FilterWheel object.

        :param id: Filter wheel ID
        :type id: str
        :param filters: Dictionary of filters
        :type filters: dict
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.id = id
        self.filters = filters
        for filter in filters:
            FILTERS.append(filter)
        # force homing of the wheel to first position
        self.filter = FILTERS[0]

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
        if filter_name not in FILTERS:
            raise ValueError(f"Filter {filter_name} not in filter list: {FILTERS}")
        self._filter = filter_name
        time.sleep(SWITCH_TIME_S)

    def close(self):
        """
        Close the filter wheel device.
        """
        pass
