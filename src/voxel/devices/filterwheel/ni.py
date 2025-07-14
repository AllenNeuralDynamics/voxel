import logging
import nidaqmx
import numpy
import time

from nidaqmx.constants import AcquisitionType as AcqType, AOIdleOutputBehavior
from voxel.devices.daq.ni import NIDAQ
from voxel.devices.filterwheel.base import BaseFilterWheel

MAX_VOLTS = 5.0
SAMPLING_FREQUENCY_HZ = 10000
PERIOD_TIME_MS = 100
DUTY_CYCLE_PERCENT = 50

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
        for key, value in list(ports.items()):
            if key not in filters:
                raise ValueError(f"Port {key} not in filter list: {filters}")
            if f"{daq.id}/{value}" not in daq.dev.ao_physical_chans.channel_names:
                raise ValueError(f"Port {value} not in device channels: {daq.dev.ao_physical_chans.channel_names}")
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
        channel_port = self.ports[filter_name]
        self._filter = filter_name
        self.log.info("creating change position task")
        filter_position_task = nidaqmx.Task("filter_position_task")
        physical_name = f"/{self.id}/{channel_port}"
        self.log.info("adding port to change position task")
        filter_position_task.ao_channels.add_ao_voltage_chan(physical_name)
        # channel_options.ao_idle_output_behavior = AOIdleOutputBehavior.ZERO_VOLTS
        self.log.info("configuring change position task timing")
        period_samples = int(PERIOD_TIME_MS / 1000 * SAMPLING_FREQUENCY_HZ)
        filter_position_task.timing.cfg_samp_clk_timing(
            rate=SAMPLING_FREQUENCY_HZ,
            sample_mode=AcqType.FINITE,
            samps_per_chan=period_samples,
        )
        ao_voltages = numpy.zeros(period_samples)
        ao_voltages[0 : int(period_samples * DUTY_CYCLE_PERCENT / 100)] = MAX_VOLTS
        self.log.info("writing change position voltages to task")
        filter_position_task.write(ao_voltages)
        self.log.info("starting change position task")
        filter_position_task.start()
        self.log.info("waiting on change position task")
        filter_position_task.wait_until_done()
        self.log.info("stopping change position task")
        filter_position_task.stop()
        self.log.info("closing change position task")
        filter_position_task.close()
        self.log.info(f"filter set to {filter_name}")

    def close(self) -> None:
        """
        Close the filter wheel device.
        """
        self.log.info("closing filter wheel.")
        pass
