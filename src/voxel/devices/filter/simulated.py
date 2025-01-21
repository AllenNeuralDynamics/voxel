import logging

from voxel.devices.filter.base import BaseFilter
from voxel.devices.filterwheel.simulated import SimulatedFilterWheel


class Filter(BaseFilter):
    """
    Filter class for handling simulated filter devices.
    """
    def __init__(self, wheel: SimulatedFilterWheel, id: str) -> None:
        """
        Initialize the Filter object.

        :param wheel: Filter wheel object
        :type wheel: FilterWheel
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