from abc import abstractmethod
from typing import Dict, Optional

import matplotlib.pyplot as plt
import numpy
from matplotlib.ticker import AutoMinorLocator
from scipy import interpolate, signal

from voxel.devices.base import VoxelDevice

DO_WAVEFORMS = ["square"]

AO_WAVEFORMS = ["sine", "square", "sawtooth", "triangle", "nonlinear sawtooth"]


class BaseDAQ(VoxelDevice):
    """Base class for DAQ devices."""

    @abstractmethod
    def add_task(self, task_type: str, pulse_count: Optional[int] = None) -> None:
        """
        Add a task to the DAQ.

        :param task_type: Type of the task ('ao', 'co', 'do')
        :type task_type: str
        :param pulse_count: Number of pulses for the task, defaults to None
        :type pulse_count: int, optional
        """
        pass

    @abstractmethod
    def write_ao_waveforms(self) -> None:
        """
        Write analog output waveforms to the DAQ.
        """
        pass

    @abstractmethod
    def write_do_waveforms(self) -> None:
        """
        Write digital output waveforms to the DAQ.
        """
        pass

    @abstractmethod
    def plot_waveforms_to_pdf(self) -> None:
        """
        Plot waveforms and optionally save to a PDF.
        """
        pass

    @abstractmethod
    def start(self) -> None:
        """
        Start all tasks.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """
        Stop all tasks.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close all tasks.
        """
        pass

    @abstractmethod
    def restart(self) -> None:
        """
        Restart all tasks.
        """
        pass

    @abstractmethod
    def wait_until_done_all(self, timeout: float = 1.0) -> None:
        """
        Wait until all tasks are done.

        :param timeout: Timeout in seconds, defaults to 1.0
        :type timeout: float, optional
        """
        pass

    @abstractmethod
    def is_finished_all(self) -> bool:
        """
        Check if all tasks are finished.

        :return: True if all tasks are finished, False otherwise
        :rtype: bool
        """
        pass

    @property
    def tasks(self) -> Optional[Dict[str, dict]]:
        """
        Get the tasks dictionary.

        :return: Dictionary of tasks
        :rtype: dict
        """
        return self._tasks

    @tasks.setter
    def tasks(self, tasks_dict: Dict[str, dict]) -> None:
        """
        Set the tasks dictionary.

        :param tasks_dict: Dictionary of tasks
        :type tasks_dict: dict
        """
        self._tasks = tasks_dict
        # store properties
        # store all port values as attributes for access later
        # for name, task in tasks_dict.items():
        #     if name == "ao_task":
        #         for name, specs in task["ports"].items():
        #             for parameter in specs["parameters"]:
        #                 for channel, value in specs["parameters"][parameter]["channels"].items():
        #                     parameter_name = f"daq_{name}_{parameter}_{channel}".replace(" ", "_")
        #                     eval(
        #                         f"setattr(NIDAQ, '{parameter_name}', property(fget=lambda NIDAQ: {value}, \
        #                         fset=lambda NIDAQ, value: {value}, fdel=lambda NIDAQ: None))"
        #                     )

    def sawtooth(
        self,
        repeat: bool,
        sampling_frequency_hz: float,
        period_time_ms: float,
        delay_time_ms: float,
        peak_time_ms: float,
        end_time_ms: float,
        rest_time_ms: float,
        amplitude_volts: float,
        offset_volts: float,
        cutoff_frequency_hz: float = 0,
    ) -> numpy.ndarray:
        """
        Generate a sawtooth waveform.

        :param repeat: Whether to repeat the waveform
        :type repeat: bool
        :param sampling_frequency_hz: Sampling frequency in Hz
        :type sampling_frequency_hz: float
        :param period_time_ms: Period time in milliseconds
        :type period_time_ms: float
        :param delay_time_ms: Start time in milliseconds
        :type delay_time_ms: float
        :param peak_time_ms: Peak time in milliseconds
        :type peak_time_ms: float
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
        period_samples = int(((period_time_ms - delay_time_ms) / 1000) * sampling_frequency_hz)
        waveform_samples = int(((end_time_ms - delay_time_ms) / 1000) * sampling_frequency_hz)
        time_samples_ms = numpy.linspace(0, 2 * numpy.pi, waveform_samples)
        waveform = offset_volts + amplitude_volts * signal.sawtooth(t=time_samples_ms, width=peak_time_ms / end_time_ms)
        repeat_number = numpy.floor(period_samples / waveform_samples)
        if repeat:
            waveform = numpy.tile(waveform, int(repeat_number))
            self.log.info(
                f"repeating waveform {repeat_number} times. "
                f"total samples is {len(waveform)} samples out of {period_samples} samples"
            )
            waveform = numpy.pad(
                array=waveform,
                pad_width=(0, period_samples - len(waveform)),
                mode="constant",
                constant_values=(offset_volts - amplitude_volts),
            )
        else:
            waveform = numpy.pad(
                array=waveform,
                pad_width=(0, period_samples - waveform_samples),
                mode="constant",
                constant_values=(offset_volts - amplitude_volts),
            )
        # add in delay
        delay_samples = int((delay_time_ms / 1000) * sampling_frequency_hz)
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

        if cutoff_frequency_hz > 0:
            # bessel filter order 6, cutoff frequency is normalied from 0-1 by nyquist frequency
            b, a = signal.bessel(6, cutoff_frequency_hz / (sampling_frequency_hz / 2), btype="low")

            # pad before filtering with last value
            padding = int(2 / (cutoff_frequency_hz / (sampling_frequency_hz)))
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
                waveform = waveform[padding:-padding]

        return waveform

    def nonlinear_sawtooth(
        self,
        repeat: bool,
        sampling_frequency_hz: float,
        period_time_ms: float,
        delay_time_ms: float,
        peak_time_ms: float,
        end_time_ms: float,
        rest_time_ms: float,
        amplitude_volts: float,
        offset_volts: float,
        t0_offset_volts: float,
        t50_offset_volts: float,
        t100_offset_volts: float,
    ) -> numpy.ndarray:
        """
        Generate a sawtooth waveform.

        :param repeat: Whether to repeat the waveform
        :type repeat: bool
        :param sampling_frequency_hz: Sampling frequency in Hz
        :type sampling_frequency_hz: float
        :param period_time_ms: Period time in milliseconds
        :type period_time_ms: float
        :param delay_time_ms: Start time in milliseconds
        :type delay_time_ms: float
        :param peak_time_ms: Peak time in milliseconds
        :type peak_time_ms: float
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
        period_samples = int(((period_time_ms - delay_time_ms) / 1000) * sampling_frequency_hz)
        waveform_samples = int(((end_time_ms - delay_time_ms) / 1000) * sampling_frequency_hz)
        time_samples_ms = numpy.linspace(0, 2 * numpy.pi, waveform_samples)
        waveform = offset_volts + amplitude_volts * signal.sawtooth(t=time_samples_ms, width=peak_time_ms / end_time_ms)
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

        repeat_number = numpy.floor(period_samples / waveform_samples)
        if repeat:
            waveform = numpy.tile(waveform, int(repeat_number))
            self.log.info(
                f"repeating waveform {repeat_number} times. "
                f"total samples is {len(waveform)} samples out of {period_samples} samples"
            )
            waveform = numpy.pad(
                array=waveform,
                pad_width=(0, period_samples - len(waveform)),
                mode="constant",
                constant_values=(offset_volts - amplitude_volts),
            )
        else:
            waveform = numpy.pad(
                array=waveform,
                pad_width=(0, period_samples - waveform_samples),
                mode="constant",
                constant_values=(offset_volts - amplitude_volts),
            )
        # add in delay
        delay_samples = int((delay_time_ms / 1000) * sampling_frequency_hz)
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

        return waveform

    def square(
        self,
        repeat: bool,
        sampling_frequency_hz: float,
        period_time_ms: float,
        delay_time_ms: float,
        fall_time_ms: float,
        end_time_ms: float,
        rest_time_ms: float,
        max_volts: float,
        min_volts: float,
    ) -> numpy.ndarray:
        """
        Generate a square waveform.

        :param repeat: Whether to repeat the waveform
        :type repeat: bool
        :param sampling_frequency_hz: Sampling frequency in Hz
        :type sampling_frequency_hz: float
        :param period_time_ms: Period time in milliseconds
        :type period_time_ms: float
        :param delay_time_ms: Start time in milliseconds
        :type delay_time_ms: float
        :param end_time_ms: End time in milliseconds
        :type fall_time_ms: float
        :param fall_time_ms: Fall time in milliseconds
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
        period_samples = int(((period_time_ms - delay_time_ms) / 1000) * sampling_frequency_hz)
        waveform_samples = int(((end_time_ms - delay_time_ms) / 1000) * sampling_frequency_hz)
        waveform = numpy.zeros(waveform_samples) + min_volts
        fall_sample = int(((fall_time_ms - delay_time_ms) / 1000) * sampling_frequency_hz)
        waveform[0:fall_sample] = max_volts

        repeat_number = numpy.floor(period_samples / waveform_samples)
        if repeat:
            waveform = numpy.tile(waveform, int(repeat_number))
            self.log.info(
                f"repeating waveform {repeat_number} times. "
                f"total samples is {len(waveform)} samples out of {period_samples} samples"
            )
            waveform = numpy.pad(
                array=waveform,
                pad_width=(0, period_samples - len(waveform)),
                mode="constant",
                constant_values=min_volts,
            )
        else:
            waveform = numpy.pad(
                array=waveform,
                pad_width=(0, period_samples - waveform_samples),
                mode="constant",
                constant_values=min_volts,
            )

        # add in delay
        delay_samples = int((delay_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(delay_samples, 0),
            mode="constant",
            constant_values=min_volts,
        )

        # add in rest
        rest_samples = int((rest_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(0, rest_samples),
            mode="constant",
            constant_values=min_volts,
        )

        return waveform

    def triangle(
        self,
        repeat: bool,
        sampling_frequency_hz: float,
        period_time_ms: float,
        delay_time_ms: float,
        end_time_ms: float,
        rest_time_ms: float,
        amplitude_volts: float,
        offset_volts: float,
        cutoff_frequency_hz: float,
    ) -> numpy.ndarray:
        """
        Generate a triangle waveform.

        :param repeat: Whether to repeat the waveform
        :type repeat: bool
        :param sampling_frequency_hz: Sampling frequency in Hz
        :type sampling_frequency_hz: float
        :param period_time_ms: Period time in milliseconds
        :type period_time_ms: float
        :param delay_time_ms: Start time in milliseconds
        :type delay_time_ms: float
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
            repeat,
            sampling_frequency_hz,
            period_time_ms,
            delay_time_ms,
            (end_time_ms - delay_time_ms) / 2,
            end_time_ms,
            rest_time_ms,
            amplitude_volts,
            offset_volts,
            cutoff_frequency_hz,
        )

        return waveform

    def sine(
        self,
        repeat: bool,
        sampling_frequency_hz: float,
        period_time_ms: float,
        delay_time_ms: float,
        end_time_ms: float,
        rest_time_ms: float,
        amplitude_volts: float,
        offset_volts: float,
    ) -> numpy.ndarray:
        """
        Generate a sawtooth waveform.

        :param repeat: Whether to repeat the waveform
        :type repeat: bool
        :param sampling_frequency_hz: Sampling frequency in Hz
        :type sampling_frequency_hz: float
        :param period_time_ms: Period time in milliseconds
        :type period_time_ms: float
        :param delay_time_ms: Start time in milliseconds
        :type delay_time_ms: float
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
        period_samples = int(((period_time_ms - delay_time_ms) / 1000) * sampling_frequency_hz)
        waveform_samples = int(((end_time_ms - delay_time_ms) / 1000) * sampling_frequency_hz)
        time_samples_ms = numpy.linspace(0, 2 * numpy.pi, waveform_samples)
        waveform = offset_volts + amplitude_volts * numpy.sin(time_samples_ms)
        repeat_number = numpy.floor(period_samples / waveform_samples)
        if repeat:
            waveform = numpy.tile(waveform, int(repeat_number))
            self.log.info(
                f"repeating waveform {repeat_number} times. "
                f"total samples is {len(waveform)} samples out of {period_samples} samples"
            )
            waveform = numpy.pad(
                array=waveform,
                pad_width=(0, period_samples - len(waveform)),
                mode="constant",
                constant_values=(offset_volts),
            )
        else:
            waveform = numpy.pad(
                array=waveform,
                pad_width=(0, period_samples - waveform_samples),
                mode="constant",
                constant_values=(offset_volts),
            )

        # add in delay
        delay_samples = int((delay_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(delay_samples, 0),
            mode="constant",
            constant_values=(offset_volts),
        )

        # add in rest
        rest_samples = int((rest_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(0, rest_samples),
            mode="constant",
            constant_values=(offset_volts),
        )

        return waveform

    def generate_waveforms(self, task_type: str, wavelength: str) -> None:
        """
        Generate waveforms for the task.

        :param task_type: Type of the task ('ao', 'do')
        :type task_type: str
        :param wavelength: Wavelength for the waveform
        :type wavelength: str
        :raises ValueError: If any parameter is invalid or out of range
        """
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

            repeat = channel["repeat"]
            if repeat not in [True, False]:
                raise ValueError("repeat must be True or False")
            delay_time_ms = channel["parameters"]["delay_time_ms"]["channels"][wavelength]
            if delay_time_ms > timing["period_time_ms"]:
                raise ValueError("start time must be < period time")
            end_time_ms = channel["parameters"]["end_time_ms"]["channels"][wavelength]
            if end_time_ms > timing["period_time_ms"] + timing["rest_time_ms"] or end_time_ms < delay_time_ms:
                raise ValueError("end time must be < period time and > start time")

            if waveform == "sine":
                try:
                    amplitude_volts = channel["parameters"]["amplitude_volts"]["channels"][wavelength]
                    offset_volts = channel["parameters"]["offset_volts"]["channels"][wavelength]
                    if offset_volts < self.min_ao_volts or offset_volts > self.max_ao_volts:
                        raise ValueError(
                            f"min volts must be > {self.min_ao_volts} volts and < {self.max_ao_volts} volts"
                        )
                except AttributeError:
                    raise ValueError("missing input parameter for sine wave")
                voltages = self.sine(
                    repeat,
                    timing["sampling_frequency_hz"],
                    timing["period_time_ms"],
                    delay_time_ms,
                    end_time_ms,
                    timing["rest_time_ms"],
                    amplitude_volts,
                    offset_volts,
                )

            if waveform == "square":
                try:
                    fall_time_ms = channel["parameters"]["fall_time_ms"]["channels"][wavelength]
                    max_volts = channel["parameters"]["max_volts"]["channels"][wavelength] if task_type == "ao" else 5
                    if max_volts > self.max_ao_volts:
                        raise ValueError(f"max volts must be < {self.max_ao_volts} volts")
                    min_volts = channel["parameters"]["min_volts"]["channels"][wavelength] if task_type == "ao" else 0
                    if min_volts < self.min_ao_volts:
                        raise ValueError(f"min volts must be > {self.min_ao_volts} volts")
                except AttributeError:
                    raise ValueError("missing input parameter for square wave")
                voltages = self.square(
                    repeat,
                    timing["sampling_frequency_hz"],
                    timing["period_time_ms"],
                    delay_time_ms,
                    fall_time_ms,
                    end_time_ms,
                    timing["rest_time_ms"],
                    max_volts,
                    min_volts,
                )

            if waveform == "sawtooth":  # setup is same for both waves, only be ao task
                try:
                    peak_time_ms = channel["parameters"]["peak_time_ms"]["channels"][wavelength]
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
                    repeat,
                    timing["sampling_frequency_hz"],
                    timing["period_time_ms"],
                    delay_time_ms,
                    peak_time_ms,
                    end_time_ms,
                    timing["rest_time_ms"],
                    amplitude_volts,
                    offset_volts,
                    cutoff_frequency_hz,
                )

            if waveform == "nonlinear sawtooth":
                try:
                    peak_time_ms = channel["parameters"]["peak_time_ms"]["channels"][wavelength]
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
                voltages = self.nonlinear_sawtooth(
                    repeat,
                    timing["sampling_frequency_hz"],
                    timing["period_time_ms"],
                    delay_time_ms,
                    peak_time_ms,
                    end_time_ms,
                    timing["rest_time_ms"],
                    amplitude_volts,
                    offset_volts,
                    t0_offset_volts,
                    t50_offset_volts,
                    t100_offset_volts,
                )

            if waveform == "triangle":  # setup is same for both waves, only be ao task
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
                    repeat,
                    timing["sampling_frequency_hz"],
                    timing["period_time_ms"],
                    delay_time_ms,
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

        # store these values as properties for plotting purposes
        setattr(self, f"{task_type}_sampling_frequency_hz", timing["sampling_frequency_hz"])
        setattr(self, f"{task_type}_total_time_ms", timing["period_time_ms"] + timing["rest_time_ms"])

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
            time_ms = numpy.linspace(
                0, self.ao_total_time_ms, int(numpy.ceil(self.ao_total_time_ms / 1000 * self.ao_sampling_frequency_hz))
            )
            for waveform in self.ao_waveforms:
                plt.plot(time_ms, self.ao_waveforms[waveform], label=waveform)
        if self.do_waveforms:
            time_ms = numpy.linspace(
                0, self.do_total_time_ms, int(self.do_total_time_ms / 1000 * self.do_sampling_frequency_hz)
            )
            for waveform in self.do_waveforms:
                plt.plot(time_ms, self.do_waveforms[waveform], label=waveform)

        plt.axis([0, numpy.max([self.ao_total_time_ms, self.do_total_time_ms]), self.min_ao_volts, self.max_ao_volts])
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.spines[["right", "top"]].set_visible(False)
        ax.set_xlabel("time, ms")
        ax.set_ylabel("amplitude, volts")
        ax.legend(loc="upper right", fontsize=10, edgecolor=None)
        ax.tick_params(which="major", direction="out", length=8, width=0.75)
        ax.tick_params(which="minor", length=4)
        if save:
            plt.savefig("./waveforms.pdf", bbox_inches="tight")

    def _timing_checks(self, task_type: str) -> None:
        """
        Check period time, rest time, and sample frequency.

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
