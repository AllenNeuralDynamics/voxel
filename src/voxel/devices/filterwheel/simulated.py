import logging
import time
from typing import Dict

from voxel.devices.filterwheel.base import BaseFilterWheel

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
        # force homing of the wheel
        self.filter = next(key for key, value in self.filters.items() if value == 0)
        # store simulated index internally
        self._filter = 0

    @property
    def filter(self) -> str:
        """
        Get the current filter.

        :return: Current filter name
        :rtype: str
        """
        return next(key for key, value in self.filters.items() if value == self._filter)

    @filter.setter
    def filter(self, filter_name: str) -> None:
        """
        Set the current filter.

        :param filter_name: Filter name
        :type filter_name: str
        """
        self.log.info(f"setting filter to {filter_name}")
        self._filter = self.filters[filter_name]
        time.sleep(SWITCH_TIME_S)

    def close(self) -> None:
        """
        Close the simulated filter wheel.
        """
        pass
