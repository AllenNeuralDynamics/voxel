import logging

from voxel.devices.daq.ni import NIDAQ
from voxel.devices.filterwheel.base import BaseFilterWheel

FILTERS = list()


class DAQFilterWheel(BaseFilterWheel):
    """
    FilterWheel class for handling simulated filter wheel devices.
    """

    def __init__(self, filters: dict, ports: dict, daq: NIDAQ = None) -> None:
        """
        Initialize the FilterWheel object.

        :param filters: Dictionary of filters
        :type filters: dict
        :param ports: Dictionary of filter ports
        :type ports: dict
        :param daq: NI-DAQmx device
        :type daq: NIDAQ
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.id = daq.id
        self.dev = daq
        self.ports = ports
        self.filters = filters
        for filter in filters:
            FILTERS.append(filter)
            if filter not in list(ports.keys()):
                raise ValueError(f"Filter {filter} not in port keys: {list(ports.keys())}")
        # for key, value in list(ports.items()):
        #     if key not in filters:
        #         raise ValueError(f"Port {key} not in filter list: {filters}")
        #     if f"{daq.id}/{value}" not in daq.dev.ao_physical_chans.channel_names:
        #         raise ValueError(f"Port {value} not in device channels: {daq.dev.ao_physical_chans.channel_names}")
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
        channel_port = self.ports[filter_name]
        self.dev.change_filter_position(channel_port)
        self.log.info(f"filter set to {filter_name}")

    def close(self) -> None:
        """
        Close the filter wheel device.
        """
        pass
