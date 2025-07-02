import logging
import time

from voxel.devices.controller.asi.tiger import TigerController

from voxel.devices.filterwheel.base import BaseFilterWheel

FILTERS = list()

SWITCH_TIME_S = 0.1  # estimated timing


class FW1000FilterWheel(BaseFilterWheel):
    """
    FilterWheel class for handling ASI filter wheel devices.
    """

    def __init__(self, tigerbox: TigerController, id: str, filters: dict) -> None:
        """
        Initialize the FilterWheel object.

        :param tigerbox: TigerController object
        :type tigerbox: TigerController
        :param id: Filter wheel ID
        :type id: str
        :param filters: Dictionary of filters
        :type filters: dict
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tigerbox = tigerbox
        self.id = id
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
        if filter_name not in FILTERS:
            raise ValueError(f"Filter {filter_name} not in filter list: {FILTERS}")
        self._filter = filter_name
        cmd_str = f"MP {self.filters[filter_name]}\r\n"
        self.log.info(f"setting filter to {filter_name}")
        # Note: the filter wheel has slightly different reply line termination.
        self.tigerbox.send(f"FW {self.id}\r\n", read_until=f"\n\r{self.id}>")
        self.tigerbox.send(cmd_str, read_until=f"\n\r{self.id}>")
        # TODO: add "busy" check because tigerbox.is_moving() doesn't apply to filter wheels.
        time.sleep(SWITCH_TIME_S)

    def close(self) -> None:
        """
        Close the filter wheel device.
        """
        self.log.info("closing filter wheel.")
        pass
