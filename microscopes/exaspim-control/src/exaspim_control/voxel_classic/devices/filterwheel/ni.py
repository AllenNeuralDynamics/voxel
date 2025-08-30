import nidaqmx
import numpy
from exaspim_control.voxel_classic.devices.daq.ni import NIDAQ
from exaspim_control.voxel_classic.devices.filterwheel.base import BaseFilterWheel
from nidaqmx.constants import AcquisitionType as AcqType

MAX_VOLTS = 5.0
SAMPLING_FREQUENCY_HZ = 10000
PERIOD_TIME_MS = 100
DUTY_CYCLE_PERCENT = 50


class DAQFilterWheel(BaseFilterWheel):
    """FilterWheel class for handling simulated filter wheel devices."""

    def __init__(self, uid: str, filters: dict[str, int], ports: dict[str, str], daq: NIDAQ) -> None:
        """Initialize the FilterWheel object.

        :param filters: List of filter names
        :type filters: list[str]
        :param ports: Dictionary of filter ports
        :type ports: dict
        :param daq: NI-DAQmx device
        :type daq: NIDAQ
        """
        super().__init__(uid)

        self.id = daq.id
        self.dev = daq
        self.ports = ports
        filters_keys = set(filters.keys())
        ports_keys = set(ports.keys())
        difference = filters_keys.symmetric_difference(ports_keys)
        if difference:
            raise ValueError(f'Filters and ports keys do not match: {difference}')

        for port in ports.values():
            if f'{daq.id}/{port}' not in daq.dev.ao_physical_chans.channel_names:
                raise ValueError(f'Port {port} not in device channels: {daq.dev.ao_physical_chans.channel_names}')
        # force homing of the wheel to first position
        self._filters: dict[str, int] = {filter_name: i for i, filter_name in enumerate(filters)}
        self.filter = next(iter(self._filters.keys()))

    @property
    def filters(self) -> dict[str, int]:
        """Get the list of available filters."""
        return self._filters

    @property
    def filter(self) -> str:
        """Get the current filter.

        :return: Current filter name
        :rtype: str
        """
        return self._filter

    @filter.setter
    def filter(self, filter_name: str) -> None:
        """Set the current filter.

        :param filter_name: Filter name
        :type filter_name: str
        """
        self.log.info(f'setting filter to {filter_name}')
        if filter_name not in self._filters:
            raise ValueError(f'Filter {filter_name} not in filter list: {self._filters}')
        channel_port = self.ports[filter_name]
        self._filter = filter_name
        self.log.debug('creating change position task')
        filter_position_task = nidaqmx.Task('filter_position_task')
        physical_name = f'/{self.id}/{channel_port}'
        self.log.debug('adding port to change position task')
        filter_position_task.ao_channels.add_ao_voltage_chan(physical_name)
        # channel_options.ao_idle_output_behavior = AOIdleOutputBehavior.ZERO_VOLTS
        self.log.debug('configuring change position task timing')
        period_samples = int(PERIOD_TIME_MS / 1000 * SAMPLING_FREQUENCY_HZ)
        filter_position_task.timing.cfg_samp_clk_timing(
            rate=SAMPLING_FREQUENCY_HZ,
            sample_mode=AcqType.FINITE,
            samps_per_chan=period_samples,
        )
        ao_voltages = numpy.zeros(period_samples)
        ao_voltages[0 : int(period_samples * DUTY_CYCLE_PERCENT / 100)] = MAX_VOLTS
        self.log.debug('writing change position voltages to task')
        filter_position_task.write(ao_voltages)
        self.log.debug('starting change position task')
        filter_position_task.start()
        self.log.debug('waiting on change position task')
        filter_position_task.wait_until_done()
        self.log.debug('stopping change position task')
        filter_position_task.stop()
        self.log.debug('closing change position task')
        filter_position_task.close()
        self.log.info(f'filter set to {filter_name}')

    def close(self) -> None:
        """Close the filter wheel device."""
        self.log.info('closing filter wheel.')
