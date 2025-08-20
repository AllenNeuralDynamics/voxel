import math
import time

import matplotlib.pyplot as plt
import nidaqmx
import numpy as np
from matplotlib.ticker import AutoMinorLocator
from nidaqmx.constants import AcquisitionType as AcqType
from nidaqmx.constants import AOIdleOutputBehavior, Edge, FrequencyUnits, Slope
from nidaqmx.system.system import System as NIDAQSystem
from nidaqmx.system.device import Device as NIDAQDevice
from scipy import interpolate, signal
from voxel_classic.devices.daq.base import BaseDAQ

DO_WAVEFORMS = ["square wave"]

AO_WAVEFORMS = ["square wave", "sawtooth", "nonlinear sawtooth", "triangle wave"]

TRIGGER_MODE = ["on", "off"]

SAMPLE_MODE = {"finite": AcqType.FINITE, "continuous": AcqType.CONTINUOUS}

TRIGGER_EDGE = {"rising": Edge.RISING, "falling": Edge.FALLING}

TRIGGER_POLARITY = {
    "rising": Slope.RISING,
    "falling": Slope.FALLING,
}

RETRIGGERABLE = {"on": True, "off": False}


class NIDAQ(BaseDAQ):
    """DAQ class for handling NI DAQ devices."""

    ao_total_time_ms: float
    do_total_time_ms: float
    ao_sampling_frequency_hz: float
    do_sampling_frequency_hz: float
    ao_waveforms: dict
    do_waveforms: dict
    co_frequency_hz: float

    def __init__(self, uid: str, dev: str) -> None:
        """
        Initialize the DAQ object.

        :param dev: Device name
        :type dev: str
        :raises ValueError: If the device name is not found in the system
        """
        super().__init__(uid)
        self.do_task: nidaqmx.Task | None = None
        self.ao_task: nidaqmx.Task | None = None
        self.co_task: nidaqmx.Task | None = None
        self._tasks: dict[str, dict] = {}

        self.devs = []
        for device in NIDAQSystem.local().devices:
            self.devs.append(device.name)
        if dev not in self.devs:
            raise ValueError("dev name must be one of %r." % self.devs)
        self.id = dev
        self.dev = NIDAQDevice(self.id)
        self.log.info("resetting nidaq")
        self.dev.reset_device()
        self.ao_physical_chans = self.dev.ao_physical_chans.channel_names
        self.co_physical_chans = self.dev.co_physical_chans.channel_names
        self.do_physical_chans = self.dev.do_ports.channel_names
        self.dio_ports = [channel.replace("port", "PFI") for channel in self.dev.do_ports.channel_names]
        self.dio_lines = self.dev.di_lines.channel_names
        self.max_ao_rate = self.dev.ao_max_rate
        self.min_ao_rate = self.dev.ao_min_rate
        self.max_do_rate = self.dev.do_max_rate
        self.max_ao_volts = self.dev.ao_voltage_rngs[1]
        self.min_ao_volts = self.dev.ao_voltage_rngs[0]
        self.task_time_s = {}
        self.ao_waveforms = {}
        self.do_waveforms = {}

    @property
    def tasks(self) -> dict[str, dict]:
        """
        Get the tasks dictionary.

        :return: Dictionary of tasks
        :rtype: dict
        """
        return self._tasks

    @tasks.setter
    def tasks(self, tasks_dict: dict[str, dict]) -> None:
        """
        Set the tasks dictionary.

        :param tasks_dict: Dictionary of tasks
        :type tasks_dict: dict
        """
        self._tasks = tasks_dict
        # store properties
        # store all port values as attributes for access later
        for name, task in tasks_dict.items():
            if name == "ao_task":
                for name, specs in task["ports"].items():
                    for parameter in specs["parameters"]:
                        for channel, value in specs["parameters"][parameter]["channels"].items():
                            parameter_name = f"daq_{name}_{parameter}_{channel}".replace(" ", "_")
                            eval(
                                f"setattr(NIDAQ, '{parameter_name}', property(fget=lambda NIDAQ: {value}, \
                                fset=lambda NIDAQ, value: {value}, fdel=lambda NIDAQ: None))"
                            )

    def configure_acq_waveforms(self, channel_name: str):
        if self.tasks.get("ao_task") is None and self.tasks.get("co_task") is None:
            self.log.warning("Unable to configure daq waveforms. No AO or CO task configured in DAQ.")
            return
        self.add_ao_task()
        self.generate_waveforms(channel_name)
        self.write_waveforms()

        pulse_count = self.tasks["co_task"]["timing"].get("pulse_count", None)
        self.add_co_task(pulse_count)

    def add_ao_task(self) -> None:
        """
        Add a task to the DAQ.

        :param task_type: Type of the task ('ao', 'co', 'do')
        :type task_type: str
        :param pulse_count: Number of pulses for the task, defaults to None
        :type pulse_count: int, optional
        :raises ValueError: If the task type is invalid or if any parameter is out of range
        """

        task = self.tasks["ao_task"]
        if self.ao_task is not None:
            self.ao_task.close()  # close old task
            self.ao_task = None

        self.ao_task = nidaqmx.Task(task["name"])
        if self.ao_task is None:
            self.log.error("Failed to create AO task.")
            return

        timing = task["timing"]

        for k, v in timing.items():
            global_var = globals().get(k.upper(), {})
            valid = list(global_var.keys()) if isinstance(global_var, dict) else global_var
            if v not in valid and valid != []:
                raise ValueError(f"{k} must be one of {valid}")

        channel_options = {"ao": self.ao_physical_chans, "do": self.do_physical_chans, "co": self.co_physical_chans}

        self._timing_checks("ao")

        trigger_port = timing["trigger_port"]

        for name, specs in task["ports"].items():
            # add channel to task
            channel_port = specs["port"]
            if f"{self.id}/{channel_port}" not in channel_options["ao"]:
                raise ValueError(f"ao number must be one of {channel_options['ao']}")
            physical_name = f"/{self.id}/{channel_port}"
            channel = self.ao_task.ao_channels.add_ao_voltage_chan(physical_name)
            # maintain last voltage value
            try:
                channel.ao_idle_output_behavior = AOIdleOutputBehavior.ZERO_VOLTS
            except Exception:
                self.log.debug(
                    "could not set AOIdleOutputBehavior to MAINTAIN_EXISTING_VALUE "
                    f"on channel {physical_name} for {channel}."
                )

        total_time_ms = float(timing["period_time_ms"]) + float(timing["rest_time_ms"])
        daq_samples = int(((total_time_ms) / 1000) * timing["sampling_frequency_hz"])

        if timing["trigger_mode"] == "on":
            self.ao_task.timing.cfg_samp_clk_timing(
                rate=timing["sampling_frequency_hz"],
                sample_mode=SAMPLE_MODE[timing["sample_mode"]],
                samps_per_chan=daq_samples,
            )
            self.ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(trigger_source=f"/{self.id}/{trigger_port}")
            self.ao_task.triggers.start_trigger.retriggerable = RETRIGGERABLE[timing["retriggerable"]]
        else:
            self.ao_task.timing.cfg_samp_clk_timing(
                rate=timing["sampling_frequency_hz"],
                sample_mode=SAMPLE_MODE[timing["sample_mode"]],
                samps_per_chan=int((timing["period_time_ms"] / 1000) / timing["sampling_frequency_hz"]),
            )

        # Note: Removed obsolete line_states_done_state and line_states_paused_state setters
        # These attributes don't exist on nidaqmx Task objects

        # store the total task time
        self.task_time_s[task["name"]] = total_time_ms / 1000

    def add_co_task(self, pulse_count: int | None = None):
        if self.co_task is not None:
            self.co_task.close()
            self.co_task = None

        task_cfg = self.tasks["co_task"]

        self.co_task = nidaqmx.Task(task_cfg["name"])
        if self.co_task is None:
            self.log.error("Failed to create counter output task.")
            return

        timing = task_cfg["timing"]

        for k, v in timing.items():
            global_var = globals().get(k.upper(), {})
            valid = list(global_var.keys()) if isinstance(global_var, dict) else global_var
            if v not in valid and valid != []:
                raise ValueError(f"{k} must be one of {valid}")

        if timing["frequency_hz"] < 0:
            raise ValueError("frequency must be >0 Hz")

        # configure counter output channels
        for channel_number in task_cfg["counters"]:
            if f"{self.id}/{channel_number}" not in self.co_physical_chans:
                raise ValueError("co number must be one of %r." % self.co_physical_chans)
            physical_name = f"/{self.id}/{channel_number}"
            co_chan = self.co_task.co_channels.add_co_pulse_chan_freq(
                counter=physical_name, units=FrequencyUnits.HZ, freq=timing["frequency_hz"], duty_cycle=0.5
            )
            co_chan.co_pulse_term = f"/{self.id}/{timing['output_port']}"

        if timing["trigger_mode"] == "off":
            if pulse_count is not None:
                self.co_task.timing.cfg_implicit_timing(sample_mode=AcqType.FINITE, samps_per_chan=pulse_count)
            else:
                self.co_task.timing.cfg_implicit_timing(sample_mode=AcqType.CONTINUOUS)
        else:
            raise ValueError("triggering not support for counter output tasks.")

        # store the total task time
        self.task_time_s[task_cfg["name"]] = 1 / timing["frequency_hz"]
        self.co_frequency_hz = timing["frequency_hz"]

    def _timing_checks(self, task_type: str) -> None:
        """
        Perform timing checks for the task.

        :param task_type: Type of the task ('ao', 'co', 'do')
        :type task_type: str
        :raises ValueError: If any timing parameter is out of range
        """
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

    def generate_waveforms(self, wavelength: str) -> None:
        """
        Generate waveforms for the task.

        :param task_type: Type of the task ('ao', 'do')
        :type task_type: str
        :param wavelength: Wavelength for the waveform
        :type wavelength: str
        :raises ValueError: If any parameter is invalid or out of range
        """

        # task_types = ["ao", "do"]
        task_types = ["ao"]
        for task_type in task_types:
            task = self.tasks.get(f"{task_type}_task")
            if not task:
                self.log.error(f"Unable to generate waveforms for {task_type} task. task not found")
                continue

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
                if (
                    end_time_ms > float(timing["period_time_ms"]) + float(timing["rest_time_ms"])
                    or end_time_ms < start_time_ms
                ):
                    raise ValueError("end time must be < period time and > start time")

                voltages = np.zeros((int(timing["period_time_ms"]),))

                if waveform == "square wave":
                    try:
                        max_volts = (
                            channel["parameters"]["max_volts"]["channels"][wavelength] if task_type == "ao" else 5
                        )
                        if max_volts > self.max_ao_volts:
                            raise ValueError(f"max volts must be < {self.max_ao_volts} volts")
                        min_volts = (
                            channel["parameters"]["min_volts"]["channels"][wavelength] if task_type == "ao" else 0
                        )
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

                if (
                    waveform == "sawtooth" or waveform == "triangle wave"
                ):  # setup is same for both waves, only be ao task
                    try:
                        amplitude_volts = channel["parameters"]["amplitude_volts"]["channels"][wavelength]
                        offset_volts = channel["parameters"]["offset_volts"]["channels"][wavelength]
                        if offset_volts < self.min_ao_volts or offset_volts > self.max_ao_volts:
                            raise ValueError(
                                f"min volts must be > {self.min_ao_volts} volts and < {self.max_ao_volts} volts"
                            )
                        cutoff_frequency_hz = channel["parameters"]["cutoff_frequency_hz"]["channels"][wavelength]
                        if cutoff_frequency_hz < 0:
                            raise ValueError("cutoff frequnecy must be > 0 Hz")
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

                if waveform == "nonlinear sawtooth":
                    try:
                        amplitude_volts = channel["parameters"]["amplitude_volts"]["channels"][wavelength]
                        offset_volts = channel["parameters"]["offset_volts"]["channels"][wavelength]
                        t0_offset_volts = channel["parameters"]["t0_offset_volts"]["channels"][wavelength]
                        t50_offset_volts = channel["parameters"]["t50_offset_volts"]["channels"][wavelength]
                        t100_offset_volts = channel["parameters"]["t100_offset_volts"]["channels"][wavelength]
                        if offset_volts < self.min_ao_volts or offset_volts > self.max_ao_volts:
                            raise ValueError(
                                f"min volts must be > {self.min_ao_volts} volts and < {self.max_ao_volts} volts"
                            )
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
                        t0_offset_volts,
                        t50_offset_volts,
                        t100_offset_volts,
                    )
                # sanity check voltages for ni card range
                max = getattr(self, "max_ao_volts", 5)
                min = getattr(self, "min_ao_volts", 0)
                if np.max(voltages[:]) > max or np.min(voltages[:]) < min:
                    raise ValueError(f"voltages are out of ni card range [{max}, {min}] volts")

                # sanity check voltages for device range
                if np.max(voltages[:]) > device_max_volts or np.min(voltages[:]) < device_min_volts:
                    raise ValueError(
                        f"voltages are out of device range [{device_min_volts}, {device_max_volts}] volts for {name} and {channel}"
                    )

                # store 1d voltage array into 2d waveform array

                waveform_attribute[f"{port}: {name}"] = voltages

            # store these values
            setattr(self, f"{task_type}_sampling_frequency_hz", timing["sampling_frequency_hz"])
            setattr(self, f"{task_type}_total_time_ms", float(timing["period_time_ms"]) + float(timing["rest_time_ms"]))
            setattr(self, f"{task_type}_active_edge", TRIGGER_POLARITY[timing["trigger_polarity"]])
            setattr(self, f"{task_type}_sample_mode", SAMPLE_MODE[timing["sample_mode"]])

    def write_waveforms(self, rereserve_buffer: bool = True) -> None:
        """
        Write waveforms to the DAQ.

        :param rereserve_buffer: Whether to re-reserve the buffer, defaults to True
        :type rereserve_buffer: bool, optional
        """
        ao_voltages = np.array(list(self.ao_waveforms.values()))
        if self.ao_task:
            self.ao_task.write(np.array(ao_voltages))
        else:
            self.log.error("AO task is not available. Cannot write waveforms.")

        # do_voltages = np.array(list(self.do_waveforms.values()))
        # do_voltages = do_voltages.astype("uint32")[0] if len(do_voltages) == 1 else do_voltages.astype("uint32")
        # if self.do_task:
        #     self.do_task.write(do_voltages)
        # else:
        #     self.log.error("DO task is not available. Cannot write waveforms.")

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
    ) -> np.ndarray:
        """
        Generate a sawtooth waveform.

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
        waveform_length_samples = int(((period_time_ms + rest_time_ms) / 1000) * sampling_frequency_hz)

        time_samples_ms = np.linspace(
            0, 2 * np.pi, int(((period_time_ms - start_time_ms) / 1000) * sampling_frequency_hz)
        )
        waveform = offset_volts + amplitude_volts * signal.sawtooth(
            t=time_samples_ms, width=int(end_time_ms / period_time_ms)
        )

        # add in delay
        delay_samples = int((start_time_ms / 1000) * sampling_frequency_hz)
        waveform = np.pad(
            array=waveform,
            pad_width=(delay_samples, 0),
            mode="constant",
            constant_values=(offset_volts - amplitude_volts),
        )

        # add in rest
        rest_samples = int((rest_time_ms / 1000) * sampling_frequency_hz)
        waveform = np.pad(
            array=waveform,
            pad_width=(0, rest_samples),
            mode="constant",
            constant_values=(offset_volts - amplitude_volts),
        )

        # bessel filter order 6, cutoff frequency is normalied from 0-1 by nyquist frequency
        b, a = signal.bessel(6, cutoff_frequency_hz / (sampling_frequency_hz / 2), btype="low")  # type: ignore

        # pad before filtering with last value
        padding = math.ceil(2 / (cutoff_frequency_hz / (sampling_frequency_hz)))

        if padding > 0:
            # waveform = numpy.hstack([waveform[:padding], waveform, waveform[-padding:]])
            waveform = np.pad(
                array=waveform,
                pad_width=(padding, padding),
                mode="constant",
                constant_values=(offset_volts - amplitude_volts),
            )

        # bi-directional filtering
        waveform = signal.lfilter(b, a, signal.lfilter(b, a, waveform)[::-1])[::-1]

        if padding > 0:
            waveform = waveform[padding : padding + waveform_length_samples]

        return np.asarray(waveform)

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
    ) -> np.ndarray:
        """
        Generate a sawtooth waveform.

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
        waveform_length_samples = int(((period_time_ms + rest_time_ms) / 1000) * sampling_frequency_hz)

        time_samples_ms = np.linspace(
            0, 2 * np.pi, int(((period_time_ms - start_time_ms) / 1000) * sampling_frequency_hz), retstep=False
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
        f = interpolate.interp1d([t0, t25, t50, t75, t100], [v0, v25, v50, v75, v100], kind="quadratic")
        waveform = f(time_samples_ms)

        # add in delay
        delay_samples = int((start_time_ms / 1000) * sampling_frequency_hz)
        waveform = np.pad(
            array=waveform,
            pad_width=(delay_samples, 0),
            mode="constant",
            constant_values=(offset_volts - amplitude_volts + t0_offset_volts),
        )

        # add in rest
        rest_samples = int((rest_time_ms / 1000) * sampling_frequency_hz)
        waveform = np.pad(
            array=waveform,
            pad_width=(0, rest_samples),
            mode="constant",
            constant_values=(offset_volts - amplitude_volts + t0_offset_volts),
        )

        waveform = waveform[0:waveform_length_samples]

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
    ) -> np.ndarray:
        """
        Generate a square waveform.

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
        waveform = np.zeros(time_samples) + min_volts
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
    ) -> np.ndarray:
        """
        Generate a triangle waveform.

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
        """
        Plot waveforms and optionally save to a PDF.

        :param save: Whether to save the plot to a PDF, defaults to False
        :type save: bool, optional
        """
        plt.rcParams["font.size"] = 10
        plt.rcParams["font.family"] = "Arial"
        plt.rcParams["font.weight"] = "light"
        plt.rcParams["figure.figsize"] = [6, 4]
        plt.rcParams["lines.linewidth"] = 1

        ax = plt.axes()

        if self.ao_waveforms:
            time_ms = np.linspace(
                0, self.ao_total_time_ms, int(self.ao_total_time_ms / 1000 * self.ao_sampling_frequency_hz)
            )
            for waveform in self.ao_waveforms:
                plt.plot(time_ms, self.ao_waveforms[waveform], label=waveform)
        if self.do_waveforms:
            time_ms = np.linspace(
                0, self.do_total_time_ms, int(self.do_total_time_ms / 1000 * self.do_sampling_frequency_hz)
            )
            for waveform in self.do_waveforms:
                plt.plot(time_ms, self.do_waveforms[waveform], label=waveform)
        max_time = max(self.ao_total_time_ms, self.do_total_time_ms)
        plt.xlim(0, max_time)
        plt.ylim(-0.2, 5.2)

        ax.xaxis.set_minor_locator(AutoMinorLocator())
        # plt.axis([0, np.max([self.ao_total_time_ms, self.do_total_time_ms]), -0.2, 5.2])
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

    def start(self) -> None:
        """
        Start all tasks.
        """
        self.start_acq_tasks()

    def stop(self) -> None:
        """
        Stop all tasks.
        """
        self.stop_acq_tasks()

    def start_acq_tasks(self):
        if self.ao_task is None or self.co_task is None:
            self.log.error(f"Unable to start acquisition tasks. AO: {self.ao_task is None}, CO: {self.co_task is None}")
            return
        self.co_task.start()
        self.ao_task.start()

    def stop_acq_tasks(self):
        if self.co_task is not None:
            self.co_task.stop()

        time.sleep(1.0 / self.co_frequency_hz * 1.1)

        if self.ao_task is not None:
            self.ao_task.stop()

    def close_acq_tasks(self):
        for task in [self.ao_task, self.co_task]:
            if task is not None:
                task.close()

    def close(self) -> None:
        """
        Close all tasks.
        """
        self.log.info("closing daq.")
        self.close_acq_tasks()

    def restart(self) -> None:
        """
        Restart all tasks.
        """
        self.stop()
        self.start()

    def wait_until_done_all(self, timeout: float = 10.0) -> None:
        """
        Wait until all tasks are done.

        :param timeout: Timeout in seconds, defaults to 10.0
        :type timeout: float, optional
        """
        for task in [self.ao_task, self.do_task]:
            if task is not None:
                task.wait_until_done(timeout)

    def is_finished_all(self) -> bool:
        """
        Check if all tasks are finished.

        :return: True if all tasks are finished, False otherwise
        :rtype: bool
        """
        for task in [self.ao_task, self.do_task]:
            if task is not None:
                if not task.is_task_done():
                    return False
            else:
                pass
        return True
