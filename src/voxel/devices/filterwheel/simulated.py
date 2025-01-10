import logging
import time

from voxel.devices.filterwheel.base import BaseFilterWheel

SWITCH_TIME_S = 0.1  # estimated timing


class FilterWheel(BaseFilterWheel):

    def __init__(self, id: str, filters: dict):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.id = id
        self.filters = filters
        # force homing of the wheel
        self.filter = next(key for key, value in self.filters.items() if value == 0)
        # store simulated index internally
        self._filter = 0

    @property
    def filter(self):
        return next(key for key, value in self.filters.items() if value == self._filter)

    @filter.setter
    def filter(self, filter_name: str):
        """Set the filterwheel index."""
        self.log.info(f"setting filter to {filter_name}")
        self._filter = self.filters[filter_name]
        time.sleep(SWITCH_TIME_S)
