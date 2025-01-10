import logging
import math
import matplotlib.pyplot as plt
import nidaqmx
import numpy
from matplotlib.ticker import AutoMinorLocator
from nidaqmx.constants import AcquisitionType as AcqType
from nidaqmx.constants import Edge, FrequencyUnits, Level, Slope, TaskMode, AOIdleOutputBehavior
from scipy import signal

from voxel.devices.daq.base import BaseDAQ

DO_WAVEFORMS = ["square wave"]

AO_WAVEFORMS = ["square wave", "sawtooth", "triangle wave"]

TRIGGER_MODE = ["on", "off"]

SAMPLE_MODE = {"finite": AcqType.FINITE, "continuous": AcqType.CONTINUOUS}

TRIGGER_POLARITY = {"rising": Edge.RISING, "falling": Edge.FALLING}

TRIGGER_EDGE = {
    "rising": Slope.RISING,
    "falling": Slope.FALLING,
}

RETRIGGERABLE = {"on": True, "off": False}


class DAQ(BaseDAQ):

    def __init__(self, dev: str):

        self.do_task = None
        self.ao_task = None
        self.co_task = None
        self._tasks = None

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.devs = list()
        for device in nidaqmx.system.System.local().devices:
            self.devs.append(device.name)
        if dev not in self.devs:
            raise ValueError("dev name must be one of %r." % self.devs)
        self.id = dev
        self.dev = nidaqmx.system.device.Device(self.id)
        self.log.info("resetting nidaq")
        self.dev.reset_device()
        self.ao_physical_chans = self.dev.ao_physical_chans.channel_names
        self.co_physical_chans = self.dev.co_physical_chans.channel_names
        self.do_physical_chans = self.dev.do_ports.channel_names
        self.dio_ports = [channel.replace(f"port", "PFI") for channel in self.dev.do_ports.channel_names]
        self.dio_lines = self.dev.di_lines.channel_names
        self.max_ao_rate = self.dev.ao_max_rate
        self.min_ao_rate = self.dev.ao_min_rate
        self.max_do_rate = self.dev.do_max_rate
        self.max_ao_volts = self.dev.ao_voltage_rngs[1]
        self.min_ao_volts = self.dev.ao_voltage_rngs[0]
        self.task_time_s = dict()
        self.ao_waveforms = dict()
        self.do_waveforms = dict()

    @property
    def tasks(self):
        return self._tasks

    @tasks.setter
    def tasks(self, tasks_dict: dict):
        # # Add waveforms to check if task is configured correctly
        # for task_type, task_dict in tasks_dict.items():
        #     pulse_count = task_dict['timing'].get('pulse_count', None)
        #     self.add_task(task_type[:2], pulse_count)
        self._tasks = tasks_dict

    def add_task(self, task_type: str, pulse_count=None):

        # check task type
        if task_type not in ["ao", "co", "do"]:
            raise ValueError(f"{task_type} must be one of {['ao', 'co', 'do']}")

        task = self.tasks[f"{task_type}_task"]

        if old_task := getattr(self, f"{task_type}_task", False):
            old_task.close()  # close old task
            delattr(self, f"{task_type}_task")  # Delete previously configured tasks
        daq_task = nidaqmx.Task(task["name"])
        timing = task["timing"]

        for k, v in timing.items():
            global_var = globals().get(k.upper(), {})
            valid = list(global_var.keys()) if type(global_var) == dict else global_var
            if v not in valid and valid != []:
                raise ValueError(f"{k} must be one of {valid}")

        channel_options = {"ao": self.ao_physical_chans, "do": self.do_physical_chans, "co": self.co_physical_chans}
        add_task_options = {"ao": daq_task.ao_channels.add_ao_voltage_chan, "do": daq_task.do_channels.add_do_chan}

        if task_type in ["ao", "do"]:
            self._timing_checks(task_type)

            trigger_port = timing["trigger_port"]
            # if f"{self.id}/{trigger_port}" not in self.dio_ports:
            #     raise ValueError("trigger port must be one of %r." % self.dio_ports)

            for port, specs in task["ports"].items():
                # add channel to task
                channel_port = specs["port"]
                if f"{self.id}/{channel_port}" not in channel_options[task_type]:
                    raise ValueError(f"{task_type} number must be one of {channel_options[task_type]}")
                physical_name = f"/{self.id}/{channel_port}"
                channel = add_task_options[task_type](physical_name)
                # maintain last voltage value
                if task_type == "ao":
                    try:
                        channel.ao_idle_output_behavior = AOIdleOutputBehavior.ZERO_VOLTS
                    except Exception as e:
                        self.log.debug(
                            "could not set AOIdleOutputBehavior to MAINTAIN_EXISTING_VALUE "
                            f"on channel {physical_name} for {channel}."
                        )

            total_time_ms = timing["period_time_ms"] + timing["rest_time_ms"]
            daq_samples = int(((total_time_ms) / 1000) * timing["sampling_frequency_hz"])

            if timing["trigger_mode"] == "on":
                daq_task.timing.cfg_samp_clk_timing(
                    rate=timing["sampling_frequency_hz"],
                    active_edge=TRIGGER_POLARITY[timing["trigger_polarity"]],
                    sample_mode=SAMPLE_MODE[timing["sample_mode"]],
                    samps_per_chan=daq_samples,
                )
                daq_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                    trigger_source=f"/{self.id}/{trigger_port}", trigger_edge=TRIGGER_EDGE[timing["trigger_polarity"]]
                )
                daq_task.triggers.start_trigger.retriggerable = RETRIGGERABLE[timing["retriggerable"]]
            else:
                daq_task.timing.cfg_samp_clk_timing(
                    rate=timing["sampling_frequency_hz"],
                    sample_mode=SAMPLE_MODE[timing["sample_mode"]],
                    samps_per_chan=int((timing["period_time_ms"] / 1000) / timing["sampling_frequency_hz"]),
                )

            setattr(daq_task, f"{task_type}_line_states_done_state", Level.LOW)
            setattr(daq_task, f"{task_type}_line_states_paused_state", Level.LOW)

            # store the total task time
            self.task_time_s[task["name"]] = total_time_ms / 1000

        else:  # co channel
            # if f"{self.id}/{ timing['output_port']}" not in self.dio_ports:
            #     raise ValueError("output port must be one of %r." % self.dio_ports)

            if timing["frequency_hz"] < 0:
                raise ValueError(f"frequency must be >0 Hz")

            for channel_number in task["counters"]:
                if f"{self.id}/{channel_number}" not in self.co_physical_chans:
                    raise ValueError("co number must be one of %r." % self.co_physical_chans)
                physical_name = f"/{self.id}/{channel_number}"
                co_chan = daq_task.co_channels.add_co_pulse_chan_freq(
                    counter=physical_name, units=FrequencyUnits.HZ, freq=timing["frequency_hz"], duty_cycle=0.5
                )
                co_chan.co_pulse_term = f'/{self.id}/{timing["output_port"]}'
                pulse_count = (
                    {"sample_mode": AcqType.FINITE, "samps_per_chan": pulse_count}
                    if pulse_count is not None
                    else {"sample_mode": AcqType.CONTINUOUS}
                )
            if timing["trigger_mode"] == "off":
                daq_task.timing.cfg_implicit_timing(**pulse_count)
            else:
                raise ValueError(f"triggering not support for counter output tasks.")

            # store the total task time
            self.task_time_s[task["name"]] = 1 / timing["frequency_hz"]
            setattr(self, f"{task_type}_frequency_hz", timing["frequency_hz"])

        setattr(self, f"{task_type}_task", daq_task)  # set task attribute

    def _timing_checks(self, task_type: str):
        """Check period time, rest time, and sample frequency"""

        task = self.tasks[f"{task_type}_task"]
        timing = task["timing"]

        period_time_ms = timing["period_time_ms"]
        if period_time_ms < 0:
            raise ValueError("Period time must be >0 ms")

        rest_time_ms = timing["rest_time_ms"]
        if rest_time_ms < 0:
            raise ValueError("Period time must be >0 ms")

        sampling_frequency_hz = timing["sampling_frequency_hz"]
        if sampling_frequency_hz < getattr(self, f"min_{task_type}_rate", 0) or sampling_frequency_hz > getattr(
            self, f"max_{task_type}_rate"
        ):
            raise ValueError(
                f"Sampling frequency must be > {getattr(self, f'{task_type}_min_rate', 0)} Hz and \
                                         <{getattr(self, f'{task_type}_max_rate')} Hz!"
            )

    def generate_waveforms(self, task_type: str, wavelength: str):

        # check task type
        if task_type not in ["ao", "do"]:
            raise ValueError(f"{task_type} must be one of {['ao', 'do']}")
        task = self.tasks[f"{task_type}_task"]
        self._timing_checks(task_type)

        timing = task["timing"]

        waveform_attribute = getattr(self, f"{task_type}_waveforms")
        for name, channel in task["ports"].items():
            # load waveform and variables
            port = channel["port"]
            device_min_volts = channel.get("device_min_volts", 0)
            device_max_volts = channel.get("device_max_volts", 5)
            waveform = channel["waveform"]

            valid = globals().get(f"{task_type.upper()}_WAVEFORMS")
            if waveform not in valid:
                raise ValueError("waveform must be one of %r." % valid)

            start_time_ms = channel["parameters"]["start_time_ms"]["channels"][wavelength]
            if start_time_ms > timing["period_time_ms"]:
                raise ValueError("start time must be < period time")
            end_time_ms = channel["parameters"]["end_time_ms"]["channels"][wavelength]
            if end_time_ms > timing["period_time_ms"] + timing["rest_time_ms"] or end_time_ms < start_time_ms:
                raise ValueError("end time must be < period time and > start time")

            if waveform == "square wave":
                try:
                    max_volts = channel["parameters"]["max_volts"]["channels"][wavelength] if task_type == "ao" else 5
                    if max_volts > self.max_ao_volts:
                        raise ValueError(f"max volts must be < {self.max_ao_volts} volts")
                    min_volts = channel["parameters"]["min_volts"]["channels"][wavelength] if task_type == "ao" else 0
                    if min_volts < self.min_ao_volts:
                        raise ValueError(f"min volts must be > {self.min_ao_volts} volts")
                except AttributeError:
                    raise ValueError("missing input parameter for square wave")
                voltages = self.square_wave(
                    timing["sampling_frequency_hz"],
                    timing["period_time_ms"],
                    start_time_ms,
                    end_time_ms,
                    timing["rest_time_ms"],
                    max_volts,
                    min_volts,
                )

            if waveform == "sawtooth" or waveform == "triangle wave":  # setup is same for both waves, only be ao task
                try:
                    amplitude_volts = channel["parameters"]["amplitude_volts"]["channels"][wavelength]
                    offset_volts = channel["parameters"]["offset_volts"]["channels"][wavelength]
                    if offset_volts < self.min_ao_volts or offset_volts > self.max_ao_volts:
                        raise ValueError(
                            f"min volts must be > {self.min_ao_volts} volts and < {self.max_ao_volts} volts"
                        )
                    cutoff_frequency_hz = channel["parameters"]["cutoff_frequency_hz"]["channels"][wavelength]
                    if cutoff_frequency_hz < 0:
                        raise ValueError(f"cutoff frequnecy must be > 0 Hz")
                except AttributeError:
                    raise ValueError(f"missing input parameter for {waveform}")

                waveform_function = getattr(self, waveform.replace(" ", "_"))
                voltages = waveform_function(
                    timing["sampling_frequency_hz"],
                    timing["period_time_ms"],
                    start_time_ms,
                    end_time_ms,
                    timing["rest_time_ms"],
                    amplitude_volts,
                    offset_volts,
                    cutoff_frequency_hz,
                )

            # sanity check voltages for ni card range
            max = getattr(self, "max_ao_volts", 5)
            min = getattr(self, "min_ao_volts", 0)
            if numpy.max(voltages[:]) > max or numpy.min(voltages[:]) < min:
                raise ValueError(f"voltages are out of ni card range [{max}, {min}] volts")

            # sanity check voltages for device range
            if numpy.max(voltages[:]) > device_max_volts or numpy.min(voltages[:]) < device_min_volts:
                raise ValueError(f"voltages are out of device range [{device_min_volts}, {device_max_volts}] volts")

            # store 1d voltage array into 2d waveform array

            waveform_attribute[f"{port}: {name}"] = voltages

        # store these values
        setattr(self, f"{task_type}_sampling_frequency_hz", timing["sampling_frequency_hz"])
        setattr(self, f"{task_type}_total_time_ms", timing["period_time_ms"] + timing["rest_time_ms"])
        setattr(self, f"{task_type}_active_edge", TRIGGER_POLARITY[timing["trigger_polarity"]])
        setattr(self, f"{task_type}_sample_mode", SAMPLE_MODE[timing["sample_mode"]])

    def write_ao_waveforms(self, rereserve_buffer=True):

        ao_voltages = numpy.array(list(self.ao_waveforms.values()))

        if rereserve_buffer:  # don't need to rereseve when rewriting already running tasks
            # unreserve buffer
            self.ao_task.control(TaskMode.TASK_UNRESERVE)
            # reconfigure timing
            self.ao_task.timing.cfg_samp_clk_timing(
                rate=self.ao_sampling_frequency_hz,
                active_edge=self.ao_active_edge,
                sample_mode=self.ao_sample_mode,
                samps_per_chan=len(ao_voltages[0]),
            )
            # sets buffer to length of voltages
            self.ao_task.out_stream.output_buf_size = len(ao_voltages[0])
            self.ao_task.control(TaskMode.TASK_COMMIT)
        self.ao_task.write(numpy.array(ao_voltages))

    def write_do_waveforms(self, rereserve_buffer=True):

        do_voltages = numpy.array(list(self.do_waveforms.values()))
        if rereserve_buffer:  # don't need to rereseve when rewriting already running tasks
            # unreserve buffer
            self.do_task.control(TaskMode.TASK_UNRESERVE)
            # sets buffer to length of voltages
            self.do_task.out_stream.output_buf_size = len(do_voltages[0])
            # FIXME: Really weird quirk on Micah's computer. Check if actually real
        do_voltages = do_voltages.astype("uint32")[0] if len(do_voltages) == 1 else do_voltages.astype("uint32")
        self.do_task.write(do_voltages)

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
    ):

        waveform_length_samples = int(((period_time_ms + rest_time_ms) / 1000) * sampling_frequency_hz)

        time_samples_ms = numpy.linspace(
            0, 2 * numpy.pi, int(((period_time_ms - start_time_ms) / 1000) * sampling_frequency_hz)
        )
        waveform = offset_volts + amplitude_volts * signal.sawtooth(
            t=time_samples_ms, width=end_time_ms / period_time_ms
        )

        # add in delay
        delay_samples = int((start_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(delay_samples, 0),
            mode="constant",
            constant_values=(offset_volts - amplitude_volts),
        )

        # add in rest
        rest_samples = int((rest_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(0, rest_samples),
            mode="constant",
            constant_values=(offset_volts - amplitude_volts),
        )

        # bessel filter order 6, cutoff frequency is normalied from 0-1 by nyquist frequency
        b, a = signal.bessel(6, cutoff_frequency_hz / (sampling_frequency_hz / 2), btype="low")

        # pad before filtering with last value
        padding = math.ceil(2 / (cutoff_frequency_hz / (sampling_frequency_hz)))

        if padding > 0:
            # waveform = numpy.hstack([waveform[:padding], waveform, waveform[-padding:]])
            waveform = numpy.pad(
                array=waveform,
                pad_width=(padding, padding),
                mode="constant",
                constant_values=(offset_volts - amplitude_volts),
            )

        # bi-directional filtering
        waveform = signal.lfilter(b, a, signal.lfilter(b, a, waveform)[::-1])[::-1]

        if padding > 0:
            waveform = waveform[padding : padding + waveform_length_samples]

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
    ):

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
    ):

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

    def plot_waveforms_to_pdf(self, save=False):

        plt.rcParams["font.size"] = 10
        plt.rcParams["font.family"] = "Arial"
        plt.rcParams["font.weight"] = "light"
        plt.rcParams["figure.figsize"] = [6, 4]
        plt.rcParams["lines.linewidth"] = 1

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

        plt.axis([0, numpy.max([self.ao_total_time_ms, self.do_total_time_ms]), -0.2, 5.2])
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.spines[["right", "top"]].set_visible(False)
        ax.set_xlabel("time, ms")
        ax.set_ylabel("amplitude, volts")
        ax.legend(loc="upper right", fontsize=10, edgecolor=None)
        ax.tick_params(which="major", direction="out", length=8, width=0.75)
        ax.tick_params(which="minor", length=4)
        if save:
            plt.savefig("waveforms.pdf", bbox_inches="tight")

    def _rereserve_buffer(self, buf_len):
        """If tasks are already configured, the buffer needs to be cleared and rereserved to work"""
        self.ao_task.control(TaskMode.TASK_UNRESERVE)  # Unreserve buffer
        # reconfigure timing
        self.ao_task.timing.cfg_samp_clk_timing(
            rate=self.ao_sampling_frequency_hz,
            active_edge=self.ao_active_edge,
            sample_mode=self.ao_sample_mode,
            samps_per_chan=buf_len,
        )
        self.ao_task.out_stream.output_buf_size = buf_len  # Sets buffer to length of voltages
        self.ao_task.control(TaskMode.TASK_COMMIT)

        self.do_task.control(TaskMode.TASK_UNRESERVE)  # Unreserve buffer
        self.do_task.out_stream.output_buf_size = buf_len
        self.do_task.control(TaskMode.TASK_COMMIT)

    def start(self):
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                task.start()

    def stop(self):
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                task.stop()

    def close(self):
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                task.close()

    def restart(self):
        self.stop()
        self.start()

    def wait_until_done_all(self, timeout=10.0):

        for task in [self.ao_task, self.do_task]:
            if task is not None:
                print(task)
                task.wait_until_done(timeout)

    def is_finished_all(self):

        for task in [self.ao_task, self.do_task]:
            if task is not None:
                if not task.is_task_done():
                    return False
            else:
                pass
        return True

    def close(self):
        pass
