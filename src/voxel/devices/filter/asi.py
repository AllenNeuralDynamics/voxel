import logging

from voxel.devices.filter.base import BaseFilter
from voxel.devices.filterwheel.asi.tiger import FW1000FilterWheel


class Filter(BaseFilter):
    """
    Filter class for handling ASI filter devices.
    """

    def __init__(self, wheel: FW1000FilterWheel, id: str) -> None:
        """
        Initialize the Filter object.

        :param wheel: Filter wheel object
        :type wheel: FW1000FilterWheel
        :param id: Filter ID
        :type id: str
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.id = id
        self.wheel = wheel

    def enable(self) -> None:
        """
        Enable the filter device.
        """
        self.wheel.filter = self.id

    def close(self) -> None:
        """
        Close the filter device.
        """
        self.wheel.close()
