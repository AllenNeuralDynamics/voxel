import matplotlib.pyplot as plt
import numpy
from exaspim_control.voxel_classic.devices.daq.base import BaseDAQ
from matplotlib.ticker import AutoMinorLocator
from scipy import interpolate, signal
from voxel.utils.log import VoxelLogging

# lets just simulate the PCIe-6738

MAX_AO_RATE_HZ = 350e3
MIN_AO_RATE_HZ = 1e3
MAX_DO_RATE_HZ = 350e3
MAX_AO_VOLTS = 10
MIN_AO_VOLTS = -10

AO_PHYSICAL_CHANS = [
    'ao0',
    'ao1',
    'ao2',
    'ao3',
    'ao4',
    'ao5',
    'ao6',
    'ao7',
    'ao8',
    'ao9',
    'ao10',
    'ao11',
    'ao12',
    'ao13',
    'ao14',
    'ao15',
    'ao16',
    'ao17',
    'ao18',
    'ao19',
    'ao20',
    'ao21',
    'ao22',
    'ao23',
    'ao24',
    'ao25',
    'ao26',
    'ao27',
    'ao28',
    'ao29',
    'ao30',
    'ao31',
]

CO_PHYSICAL_CHANS = ['ctr0', 'ctr1']

DO_PHYSICAL_CHANS = ['port0', 'port1']

DIO_PORTS = ['PFI0', 'PFI1']

DO_WAVEFORMS = ['square wave']

AO_WAVEFORMS = ['square wave', 'sawtooth', 'triangle wave', 'nonlinear sawtooth']


class SimulatedTask:
    def start(self) -> None:
        """Start the task."""

    def stop(self) -> None:
        """Stop the task."""

    def close(self) -> None:
        """Close the task."""

    def restart(self) -> None:
        """Restart the task."""
        self.stop()
        self.start()

    def wait_until_done(self, timeout: float) -> None:
        """Wait until the task is done.

        :param timeout: Timeout in seconds
        :type timeout: float
        """

    def is_task_done(self) -> bool:
        """Check if the task is done.

        :return: True if task is done, False otherwise
        :rtype: bool
        """
        return True


class SimulatedDAQ(BaseDAQ):
    """DAQ class for handling simulated DAQ devices."""

    # Type hints for dynamically set attributes
    ao_total_time_ms: float
    do_total_time_ms: float
    ao_sampling_frequency_hz: float
    do_sampling_frequency_hz: float

    def __init__(self, uid: str, dev: str) -> None:
        """Initialize the DAQ object.

        :param dev: Device name
        :type dev: str
        """
        super().__init__(uid)
        self.do_task: SimulatedTask | None = None
        self.ao_task: SimulatedTask | None = None
        self.co_task: SimulatedTask | None = None
        self._tasks: dict[str, dict] = {}

        self.log = VoxelLogging.get_logger(obj=self)
        self.id = dev
        self.ao_physical_chans = []
        self.co_physical_chans = []
        self.do_physical_chans = []
        self.dio_ports = []
        for channel in AO_PHYSICAL_CHANS:
            self.ao_physical_chans.append(f'{self.id}/{channel}')
        for channel in CO_PHYSICAL_CHANS:
            self.co_physical_chans.append(f'{self.id}/{channel}')
        for channel in DO_PHYSICAL_CHANS:
            self.do_physical_chans.append(f'{self.id}/{channel}')
        for port in DIO_PORTS:
            self.dio_ports.append(f'{self.id}/{port}')
        self.max_ao_rate = MAX_AO_RATE_HZ
        self.min_ao_rate = MIN_AO_RATE_HZ
        self.max_do_rate = MAX_DO_RATE_HZ
        self.max_ao_volts = MAX_AO_VOLTS
        self.min_ao_volts = MIN_AO_VOLTS
        self.log.info('resetting nidaq')
        self.task_time_s = {}
        self.ao_waveforms = {}
        self.do_waveforms = {}

    @property
    def tasks(self) -> dict[str, dict]:
        """Get the tasks dictionary.

        :return: Dictionary of tasks
        :rtype: dict
        """
        return self._tasks

    @tasks.setter
    def tasks(self, tasks_dict: dict[str, dict]) -> None:
        """Set the tasks dictionary.

        :param tasks_dict: Dictionary of tasks
        :type tasks_dict: dict
        """
        self._tasks = tasks_dict

    def add_ao_task(self) -> None:
        """Add a task to the DAQ."""
        task_type = 'ao'

        task = self.tasks[f'{task_type}_task']

        if old_task := getattr(self, f'{task_type}_task', None):
            if hasattr(old_task, 'close'):
                old_task.close()  # close old task
            delattr(self, f'{task_type}_task')  # Delete previously configured tasks
        timing = task['timing']

        for k, v in timing.items():
            global_var = globals().get(k.upper(), {})
            valid = list(global_var.keys()) if isinstance(global_var, dict) else global_var
            if v not in valid and valid != []:
                raise ValueError(f'{k} must be one of {valid}')

        channel_options = {'ao': self.ao_physical_chans, 'do': self.do_physical_chans, 'co': self.co_physical_chans}

        self._timing_checks(task_type)

        for port, specs in task['ports'].items():
            # add channel to task
            channel_port = specs['port']
            if f'{self.id}/{channel_port}' not in channel_options[task_type]:
                raise ValueError(f'{task_type} number must be one of {channel_options[task_type]}')

        total_time_ms = timing['period_time_ms'] + timing['rest_time_ms']

        if timing['trigger_mode'] == 'on':
            pass
        else:
            pass

        # store the total task time
        self.task_time_s[task['name']] = total_time_ms / 1000

        self.ao_task = SimulatedTask()

    def add_co_task(self, pulse_count: int | None = None) -> None:
        """Add a co task to the DAQ."""
        task_type = 'co'

        task = self.tasks[f'{task_type}_task']

        if old_task := getattr(self, f'{task_type}_task', None):
            if hasattr(old_task, 'close'):
                old_task.close()  # close old task
            delattr(self, f'{task_type}_task')  # Delete previously configured tasks
        timing = task['timing']

        for k, v in timing.items():
            global_var = globals().get(k.upper(), {})
            valid = list(global_var.keys()) if isinstance(global_var, dict) else global_var
            if v not in valid and valid != []:
                raise ValueError(f'{k} must be one of {valid}')

        if timing['frequency_hz'] < 0:
            raise ValueError('frequency must be >0 Hz')

        for channel_number in task['counters']:
            if f'{self.id}/{channel_number}' not in self.co_physical_chans:
                raise ValueError('co number must be one of %r.' % self.co_physical_chans)
        if timing['trigger_mode'] == 'off':
            pass
        else:
            raise ValueError('triggering not support for counter output tasks.')

        # store the total task time
        self.task_time_s[task['name']] = 1 / timing['frequency_hz']
        self.co_frequency_hz = timing['frequency_hz']

        self.co_task = SimulatedTask()

    def _timing_checks(self, task_type: str) -> None:
        """Check period time, rest time, and sample frequency.

        :param task_type: Type of the task ('ao', 'co', 'do')
        :type task_type: str
        :raises ValueError: If any timing parameter is out of range
        """
        task = self.tasks[f'{task_type}_task']
        timing = task['timing']

        period_time_ms = timing['period_time_ms']
        if period_time_ms < 0:
            raise ValueError('Period time must be >0 ms')

        rest_time_ms = timing['rest_time_ms']
        if rest_time_ms < 0:
            raise ValueError('Period time must be >0 ms')

        sampling_frequency_hz = timing['sampling_frequency_hz']
        if sampling_frequency_hz < getattr(self, f'min_{task_type}_rate', 0) or sampling_frequency_hz > getattr(
            self, f'max_{task_type}_rate'
        ):
            raise ValueError(
                f'Sampling frequency must be > {getattr(self, f"{task_type}_min_rate", 0)} Hz and \
                                         <{getattr(self, f"{task_type}_max_rate")} Hz!'
            )

    def generate_waveforms(self, wavelength: str) -> None:
        """Generate waveforms for the task.
        :param wavelength: Wavelength for the waveform
        :type wavelength: str
        :raises ValueError: If any parameter is invalid or out of range.
        """
        task_types = ['ao', 'do']
        for task_type in task_types:
            task = self.tasks.get(f'{task_type}_task')
            if task is None:
                continue
            self._timing_checks(task_type)

            timing = task['timing']

            waveform_attribute = getattr(self, f'{task_type}_waveforms')
            for name, channel in task['ports'].items():
                # load waveform and variables
                port = channel['port']
                device_min_volts = channel.get('device_min_volts', 0)
                device_max_volts = channel.get('device_max_volts', 5)
                waveform = channel['waveform']

                valid = globals().get(f'{task_type.upper()}_WAVEFORMS')
                if waveform not in valid:
                    raise ValueError('waveform must be one of %r.' % valid)

                start_time_ms = channel['parameters']['start_time_ms']['channels'][wavelength]
                if start_time_ms > timing['period_time_ms']:
                    raise ValueError('start time must be < period time')
                end_time_ms = channel['parameters']['end_time_ms']['channels'][wavelength]
                if end_time_ms > timing['period_time_ms'] + timing['rest_time_ms'] or end_time_ms < start_time_ms:
                    raise ValueError('end time must be < period time and > start time')

                # Initialize voltages array
                voltages: numpy.ndarray = numpy.array([])

                if waveform == 'square wave':
                    try:
                        max_volts = (
                            channel['parameters']['max_volts']['channels'][wavelength] if task_type == 'ao' else 5
                        )
                        if max_volts > self.max_ao_volts:
                            raise ValueError(f'max volts must be < {self.max_ao_volts} volts')
                        min_volts = (
                            channel['parameters']['min_volts']['channels'][wavelength] if task_type == 'ao' else 0
                        )
                        if min_volts < self.min_ao_volts:
                            raise ValueError(f'min volts must be > {self.min_ao_volts} volts')
                    except AttributeError:
                        raise ValueError('missing input parameter for square wave')
                    voltages = self.square_wave(
                        timing['sampling_frequency_hz'],
                        timing['period_time_ms'],
                        start_time_ms,
                        end_time_ms,
                        timing['rest_time_ms'],
                        max_volts,
                        min_volts,
                    )

                if (
                    waveform == 'sawtooth' or waveform == 'triangle wave'
                ):  # setup is same for both waves, only be ao task
                    try:
                        amplitude_volts = channel['parameters']['amplitude_volts']['channels'][wavelength]
                        offset_volts = channel['parameters']['offset_volts']['channels'][wavelength]
                        if offset_volts < self.min_ao_volts or offset_volts > self.max_ao_volts:
                            raise ValueError(
                                f'min volts must be > {self.min_ao_volts} volts and < {self.max_ao_volts} volts'
                            )
                        cutoff_frequency_hz = channel['parameters']['cutoff_frequency_hz']['channels'][wavelength]
                        if cutoff_frequency_hz < 0:
                            raise ValueError('cutoff frequnecy must be > 0 Hz')
                    except AttributeError:
                        raise ValueError(f'missing input parameter for {waveform}')

                    waveform_function = getattr(self, waveform.replace(' ', '_'))
                    voltages = waveform_function(
                        timing['sampling_frequency_hz'],
                        timing['period_time_ms'],
                        start_time_ms,
                        end_time_ms,
                        timing['rest_time_ms'],
                        amplitude_volts,
                        offset_volts,
                        cutoff_frequency_hz,
                    )

                if waveform == 'nonlinear sawtooth':
                    try:
                        amplitude_volts = channel['parameters']['amplitude_volts']['channels'][wavelength]
                        offset_volts = channel['parameters']['offset_volts']['channels'][wavelength]
                        t0_offset_volts = channel['parameters']['offset_volts']['channels'][wavelength]
                        t50_offset_volts = channel['parameters']['offset_volts']['channels'][wavelength]
                        t100_offset_volts = channel['parameters']['offset_volts']['channels'][wavelength]
                        if offset_volts < self.min_ao_volts or offset_volts > self.max_ao_volts:
                            raise ValueError(
                                f'min volts must be > {self.min_ao_volts} volts and < {self.max_ao_volts} volts'
                            )
                    except AttributeError:
                        raise ValueError(f'missing input parameter for {waveform}')

                    waveform_function = getattr(self, waveform.replace(' ', '_'))
                    print(waveform_function)
                    voltages = self.nonlinear_sawtooth(
                        timing['sampling_frequency_hz'],
                        timing['period_time_ms'],
                        start_time_ms,
                        end_time_ms,
                        timing['rest_time_ms'],
                        amplitude_volts,
                        offset_volts,
                        t0_offset_volts,
                        t50_offset_volts,
                        t100_offset_volts,
                    )

                # sanity check voltages for ni card range
                max = getattr(self, 'max_ao_volts', 5)
                min = getattr(self, 'min_ao_volts', 0)
                if numpy.max(voltages[:]) > max or numpy.min(voltages[:]) < min:
                    raise ValueError(f'voltages are out of ni card range [{max}, {min}] volts')

                # sanity check voltages for device range
                if numpy.max(voltages[:]) > device_max_volts or numpy.min(voltages[:]) < device_min_volts:
                    raise ValueError(f'voltages are out of device range [{device_min_volts}, {device_max_volts}] volts')

                # store 1d voltage array into 2d waveform array
                waveform_attribute[f'{port}: {name}'] = voltages

            # store these values as properties for plotting purposes
            setattr(self, f'{task_type}_sampling_frequency_hz', timing['sampling_frequency_hz'])
            setattr(self, f'{task_type}_total_time_ms', timing['period_time_ms'] + timing['rest_time_ms'])

    def write_waveforms(self, rereserve_buffer: bool = True) -> None:
        """Write waveforms to the DAQ.

        :param rereserve_buffer: Whether to re-reserve the buffer, defaults to True
        :type rereserve_buffer: bool, optional
        """
        if rereserve_buffer:  # don't need to rereseve when rewriting already running tasks
            pass

    def sawtooth(
        self,
        sampling_frequency_hz: float,
        period_time_ms: float,
        start_time_ms: float,
        end_time_ms: float,
        rest_time_ms: float,
        amplitude_volts: float,
        offset_volts: float,
        cutoff_frequency_hz: float,
    ) -> numpy.ndarray:
        """Generate a sawtooth waveform.

        :param sampling_frequency_hz: Sampling frequency in Hz
        :type sampling_frequency_hz: float
        :param period_time_ms: Period time in milliseconds
        :type period_time_ms: float
        :param start_time_ms: Start time in milliseconds
        :type start_time_ms: float
        :param end_time_ms: End time in milliseconds
        :type end_time_ms: float
        :param rest_time_ms: Rest time in milliseconds
        :type rest_time_ms: float
        :param amplitude_volts: Amplitude in volts
        :type amplitude_volts: float
        :param offset_volts: Offset in volts
        :type offset_volts: float
        :param cutoff_frequency_hz: Cutoff frequency in Hz
        :type cutoff_frequency_hz: float
        :return: Generated waveform
        :rtype: numpy.ndarray
        """
        time_samples_ms = numpy.linspace(
            0, 2 * numpy.pi, int(((period_time_ms - start_time_ms) / 1000) * sampling_frequency_hz), retstep=False
        )
        waveform = offset_volts + amplitude_volts * signal.sawtooth(
            t=time_samples_ms, width=int(end_time_ms / period_time_ms)
        )

        # add in delay
        delay_samples = int((start_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(delay_samples, 0),
            mode='constant',
            constant_values=(offset_volts - amplitude_volts),
        )

        # add in rest
        rest_samples = int((rest_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(0, rest_samples),
            mode='constant',
            constant_values=(offset_volts - amplitude_volts),
        )

        # bessel filter order 6, cutoff frequency is normalied from 0-1 by nyquist frequency
        b, a = signal.bessel(6, cutoff_frequency_hz / (sampling_frequency_hz / 2), btype='low')  # type: ignore

        # pad before filtering with last value
        padding = int(2 / (cutoff_frequency_hz / (sampling_frequency_hz)))
        if padding > 0:
            # waveform = numpy.hstack([waveform[:padding], waveform, waveform[-padding:]])
            waveform = numpy.pad(
                array=waveform,
                pad_width=(padding, padding),
                mode='constant',
                constant_values=(offset_volts - amplitude_volts),
            )

        # bi-directional filtering
        waveform = signal.lfilter(b, a, signal.lfilter(b, a, waveform)[::-1])[::-1]

        if padding > 0:
            waveform = waveform[padding:-padding]

        return numpy.asarray(waveform)

    def nonlinear_sawtooth(
        self,
        sampling_frequency_hz: float,
        period_time_ms: float,
        start_time_ms: float,
        end_time_ms: float,
        rest_time_ms: float,
        amplitude_volts: float,
        offset_volts: float,
        t0_offset_volts: float,
        t50_offset_volts: float,
        t100_offset_volts: float,
    ) -> numpy.ndarray:
        """Generate a sawtooth waveform.

        :param sampling_frequency_hz: Sampling frequency in Hz
        :type sampling_frequency_hz: float
        :param period_time_ms: Period time in milliseconds
        :type period_time_ms: float
        :param start_time_ms: Start time in milliseconds
        :type start_time_ms: float
        :param end_time_ms: End time in milliseconds
        :type end_time_ms: float
        :param rest_time_ms: Rest time in milliseconds
        :type rest_time_ms: float
        :param amplitude_volts: Amplitude in volts
        :type amplitude_volts: float
        :param offset_volts: Offset in volts
        :type offset_volts: float
        :param t0_offset_volts: First time point offset in volts
        :type t0_offset_volts: float
        :param t50_offset_volts: Middle time point offset in volts
        :type t50_offset_volts: float
        :param t100_offset_volts: Final time point offset in volts
        :type t100_offset_volts: float
        :return: Generated waveform
        :rtype: numpy.ndarray
        """
        time_samples_ms = numpy.linspace(
            0, 2 * numpy.pi, int(((period_time_ms - start_time_ms) / 1000) * sampling_frequency_hz)
        )
        waveform = offset_volts + amplitude_volts * signal.sawtooth(
            t=time_samples_ms, width=int(end_time_ms / period_time_ms)
        )
        waveform[-1] = waveform[-2]  # force last value to not snap back

        # add in nonlinear adjustment
        t0 = time_samples_ms[0]
        t25 = time_samples_ms[int(0.25 * len(time_samples_ms))]
        t50 = time_samples_ms[int(0.5 * len(time_samples_ms))]
        t75 = time_samples_ms[int(0.75 * len(time_samples_ms))]
        t100 = time_samples_ms[-1]
        v0 = waveform[0]
        v25 = waveform[int(0.25 * len(time_samples_ms))]
        v50 = waveform[int(0.5 * len(time_samples_ms))]
        v75 = waveform[int(0.75 * len(time_samples_ms))]
        v100 = waveform[-1]
        v0 = v0 + t0_offset_volts
        v50 = v50 + t50_offset_volts
        v100 = v100 + t100_offset_volts
        f = interpolate.interp1d([t0, t25, t50, t75, t100], [v0, v25, v50, v75, v100], kind='quadratic')
        waveform = f(time_samples_ms)
        waveform = numpy.asarray(waveform)

        # add in delay
        delay_samples = int((start_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(delay_samples, 0),
            mode='constant',
            constant_values=(offset_volts - amplitude_volts + t0_offset_volts),
        )

        # add in rest
        rest_samples = int((rest_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(0, rest_samples),
            mode='constant',
            constant_values=(offset_volts - amplitude_volts + t0_offset_volts),
        )

        return waveform

    def square_wave(
        self,
        sampling_frequency_hz: float,
        period_time_ms: float,
        start_time_ms: float,
        end_time_ms: float,
        rest_time_ms: float,
        max_volts: float,
        min_volts: float,
    ) -> numpy.ndarray:
        """Generate a square waveform.

        :param sampling_frequency_hz: Sampling frequency in Hz
        :type sampling_frequency_hz: float
        :param period_time_ms: Period time in milliseconds
        :type period_time_ms: float
        :param start_time_ms: Start time in milliseconds
        :type start_time_ms: float
        :param end_time_ms: End time in milliseconds
        :type end_time_ms: float
        :param rest_time_ms: Rest time in milliseconds
        :type rest_time_ms: float
        :param max_volts: Maximum voltage
        :type max_volts: float
        :param min_volts: Minimum voltage
        :type min_volts: float
        :return: Generated waveform
        :rtype: numpy.ndarray
        """
        time_samples = int(((period_time_ms + rest_time_ms) / 1000) * sampling_frequency_hz)
        start_sample = int((start_time_ms / 1000) * sampling_frequency_hz)
        end_sample = int((end_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.zeros(time_samples) + min_volts
        waveform[start_sample:end_sample] = max_volts

        return waveform

    def triangle_wave(
        self,
        sampling_frequency_hz: float,
        period_time_ms: float,
        start_time_ms: float,
        end_time_ms: float,
        rest_time_ms: float,
        amplitude_volts: float,
        offset_volts: float,
        cutoff_frequency_hz: float,
    ) -> numpy.ndarray:
        """Generate a triangle waveform.

        :param sampling_frequency_hz: Sampling frequency in Hz
        :type sampling_frequency_hz: float
        :param period_time_ms: Period time in milliseconds
        :type period_time_ms: float
        :param start_time_ms: Start time in milliseconds
        :type start_time_ms: float
        :param end_time_ms: End time in milliseconds
        :type end_time_ms: float
        :param rest_time_ms: Rest time in milliseconds
        :type rest_time_ms: float
        :param amplitude_volts: Amplitude in volts
        :type amplitude_volts: float
        :param offset_volts: Offset in volts
        :type offset_volts: float
        :param cutoff_frequency_hz: Cutoff frequency in Hz
        :type cutoff_frequency_hz: float
        :return: Generated waveform
        :rtype: numpy.ndarray
        """
        # sawtooth with end time in center of waveform
        waveform = self.sawtooth(
            sampling_frequency_hz,
            period_time_ms,
            start_time_ms,
            (period_time_ms - start_time_ms) / 2,
            rest_time_ms,
            amplitude_volts,
            offset_volts,
            cutoff_frequency_hz,
        )

        return waveform

    def plot_waveforms_to_pdf(self, save: bool = False) -> None:
        """Plot waveforms and optionally save to a PDF.

        :param save: Whether to save the plot to a PDF, defaults to False
        :type save: bool, optional
        """
        plt.rcParams['font.size'] = 10
        plt.rcParams['font.family'] = 'Arial'
        plt.rcParams['font.weight'] = 'light'
        plt.rcParams['figure.figsize'] = [6, 4]
        plt.rcParams['lines.linewidth'] = 1

        ax = plt.axes()

        if self.ao_waveforms:
            time_ms = numpy.linspace(
                0, self.ao_total_time_ms, int(self.ao_total_time_ms / 1000 * self.ao_sampling_frequency_hz)
            )
            for waveform in self.ao_waveforms:
                plt.plot(time_ms, self.ao_waveforms[waveform], label=waveform)
        if self.do_waveforms:
            time_ms = numpy.linspace(
                0, self.do_total_time_ms, int(self.do_total_time_ms / 1000 * self.do_sampling_frequency_hz)
            )
            for waveform in self.do_waveforms:
                plt.plot(time_ms, self.do_waveforms[waveform], label=waveform)

        max_time = max(self.ao_total_time_ms, self.do_total_time_ms)
        plt.xlim(0, max_time)
        plt.ylim(-0.2, 5.2)
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.spines[['right', 'top']].set_visible(False)
        ax.set_xlabel('time, ms')
        ax.set_ylabel('amplitude, volts')
        ax.legend(loc='upper right', fontsize=10, edgecolor=None)
        ax.tick_params(which='major', direction='out', length=8, width=0.75)
        ax.tick_params(which='minor', length=4)
        if save:
            plt.savefig('waveforms.pdf', bbox_inches='tight')

    def _rereserve_buffer(self, buf_len: int) -> None:
        """Re-reserve the buffer for tasks.

        :param buf_len: Length of the buffer
        :type buf_len: int
        """

    def start(self) -> None:
        """Start all tasks."""
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                pass

    def stop(self) -> None:
        """Stop all tasks."""
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                pass

    def close(self) -> None:
        """Close all tasks."""
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                pass

    def restart(self) -> None:
        """Restart all tasks."""
        self.stop()
        self.start()

    def wait_until_done_all(self, timeout: float = 1.0) -> None:
        """Wait until all tasks are done.

        :param timeout: Timeout in seconds, defaults to 1.0
        :type timeout: float, optional
        """
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                task.wait_until_done(timeout)

    def is_finished_all(self) -> bool:
        """Check if all tasks are finished.

        :return: True if all tasks are finished, False otherwise
        :rtype: bool
        """
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                if not task.is_task_done():
                    return False
            else:
                pass
        return True
