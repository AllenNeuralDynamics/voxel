import logging
import time
from .base import BaseFilterWheel

SWITCH_TIME_S = 0.1 # estimated timing

class FilterWheel(BaseFilterWheel):

    def __init__(self, filters: dict):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.filters = filters
        # force homing of the wheel
        self.set_filter(next(key for key, value in self.filters.items() if value == 0))
        # store simulated index internally
        self.index = 0

    def get_filter(self):
        return next(key for key, value in self.filters.items() if value == self.index)

    def set_filter(self, filter_name: str, wait=True):
        """Set the filterwheel index."""
        self.log.info(f'setting filter to: {filter_name}')
        self.index = self.filters[filter_name]
        time.sleep(SWITCH_TIME_S)