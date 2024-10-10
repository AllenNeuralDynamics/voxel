import logging
from voxel.devices.filter.base import BaseFilter
from voxel.devices.filterwheel.asi import FilterWheel


class Filter(BaseFilter):

    def __init__(self, wheel: FilterWheel, id: str):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.id = id
        self.wheel = wheel

    def enable(self):
        """Set parent filter wheel to filter"""
        self.wheel.filter = self.id

    def close(self):
        self.wheel.close()