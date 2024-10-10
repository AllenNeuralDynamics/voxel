import logging
import time
from voxel.devices.utils.singleton import Singleton
from tigerasi.tiger_controller import TigerController
from voxel.devices.filterwheel.base import BaseFilterWheel

# constants for the ASI filter wheel

SWITCH_TIME_S = 0.1 # estimated timing

#TODO: I can't get this working?
# singleton wrapper around TigerController
class TigerControllerSingleton(TigerController, metaclass=Singleton):
    def __init__(self, com_port):
        super(TigerControllerSingleton, self).__init__(com_port)
        
class FilterWheel(BaseFilterWheel):

    """Filter Wheel Abstraction from an ASI Tiger Controller."""

    def __init__(self, tigerbox: TigerController, id, filters: dict):
        """Connect to hardware.
      
        :param filterwheel_cfg: cfg for filterwheel
        :param tigerbox: TigerController instance.
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tigerbox = tigerbox
        self.id = id
        self.filters = filters
        # force homing of the wheel
        self.filter = next(key for key, value in self.filters.items() if value == 0)
        # ASI wheel has no get_index() function so store this internally
        self._filter = 0

    @property
    def filter(self):
        return self._filter

    @filter.setter
    def filter(self, filter_name: str):
        """Set the filterwheel index."""
        self._filter = filter_name
        cmd_str = f"MP {self.filters[filter_name]}\r\n"
        self.log.info(f'setting filter to {filter_name}')
        # Note: the filter wheel has slightly different reply line termination.
        self.tigerbox.send(f"FW {self.id}\r\n", read_until=f"\n\r{self.id}>")
        self.tigerbox.send(cmd_str, read_until=f"\n\r{self.id}>")
        # TODO: add "busy" check because tigerbox.is_moving() doesn't apply to filter wheels.
        time.sleep(SWITCH_TIME_S)

    def close(self):
        self.tigerbox.ser.close()