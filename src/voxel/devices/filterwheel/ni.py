import logging

import nidaqmx
import numpy
from nidaqmx.constants import TaskMode, AcquisitionType

from voxel.devices.filterwheel.base import BaseFilterWheel

FILTERS = list()


class DAQFilterWheel(BaseFilterWheel):
    """
    FilterWheel class for handling simulated filter wheel devices.
    """

    def __init__(self, dev: str, filters: dict, ports: dict) -> None:
        """
        Initialize the FilterWheel object.

        :param daq: NI-DAQmx device
        :type daq: Device
        :param filters: Dictionary of filters
        :type filters: dict
        :param ports: Dictionary of filter ports
        :type ports: dict
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.id = dev
        self.dev = nidaqmx.system.device.Device(self.id)
        self.ports = ports
        self.filters = filters
        for filter in filters:
            FILTERS.append(filter)
            if filter not in list(ports.keys()):
                raise ValueError(f"Filter {filter} not in port keys: {list(ports.keys())}")
        for key, value in list(ports.items()):
            if key not in filters:
                raise ValueError(f"Port {key} not in filter list: {filters}")
            if f"{dev}/{value}" not in self.dev.ao_physical_chans.channel_names:
                raise ValueError(f"Port {value} not in device channels: {self.dev.ao_physical_chans.channel_names}")
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
        daq_task = nidaqmx.Task("filter_wheel_task")
        physical_name = f"/{self.id}/{channel_port}"
        daq_task.ao_channels.add_ao_voltage_chan(physical_name)
        # unreserve buffer
        daq_task.control(TaskMode.TASK_UNRESERVE)
        daq_task.timing.cfg_samp_clk_timing(
            rate=10000,  # hardcode 10 kHz sampling rate
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=1000,  # hardcode 100 ms waveform
        )
        ao_voltages = numpy.zeros(1000)
        ao_voltages[0:500] = 5.0  # harcode 5 V TTL pulse for 50 ms
        daq_task.out_stream.output_buf_size = len(ao_voltages)
        daq_task.control(TaskMode.TASK_COMMIT)
        daq_task.write(ao_voltages)
        daq_task.start()
        daq_task.wait_until_done()
        daq_task.stop()
        daq_task.close()

    def close(self) -> None:
        """
        Close the filter wheel device.
        """
        pass
