from abc import abstractmethod
from typing import Optional

import numpy
from scipy import interpolate, signal

from voxel.devices.base import VoxelDevice


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
        cutoff_frequency_hz: float,
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
        time_samples_ms = numpy.linspace(
            0, 2 * numpy.pi, waveform_samples)
        waveform = offset_volts + amplitude_volts * signal.sawtooth(
            t=time_samples_ms, width=peak_time_ms / end_time_ms
        )
        repeat_number = numpy.floor(period_samples / waveform_samples)
        if repeat:
            waveform = numpy.tile(waveform, int(repeat_number))
            print(f'repeating waveform {repeat_number} times. '
                  f'total samples is {len(waveform)} samples out of {period_samples} samples')
            waveform = numpy.pad(array=waveform,
                                 pad_width=(0, period_samples - len(waveform)),
                                 mode="constant",
                                 constant_values=(offset_volts - amplitude_volts))
        else:
            waveform = numpy.pad(array=waveform,
                                 pad_width=(0, period_samples - waveform_samples),
                                 mode="constant",
                                 constant_values=(offset_volts - amplitude_volts))
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
        time_samples_ms = numpy.linspace(
            0, 2 * numpy.pi, waveform_samples)
        waveform = offset_volts + amplitude_volts * signal.sawtooth(
            t=time_samples_ms, width=peak_time_ms / end_time_ms
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

        repeat_number = numpy.floor(period_samples / waveform_samples)
        if repeat:
            waveform = numpy.tile(waveform, int(repeat_number))
            print(f'repeating waveform {repeat_number} times. '
                  f'total samples is {len(waveform)} samples out of {period_samples} samples')
            waveform = numpy.pad(array=waveform,
                                 pad_width=(0, period_samples - len(waveform)),
                                 mode="constant",
                                 constant_values=(offset_volts - amplitude_volts + t0_offset_volts))
        else:
            waveform = numpy.pad(array=waveform,
                                 pad_width=(0, period_samples - waveform_samples),
                                 mode="constant",
                                 constant_values=(offset_volts - amplitude_volts + t0_offset_volts))

        # add in delay
        delay_samples = int((delay_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(delay_samples, 0),
            mode="constant",
            constant_values=(offset_volts - amplitude_volts + t0_offset_volts),
        )

        # add in rest
        rest_samples = int((rest_time_ms / 1000) * sampling_frequency_hz)
        waveform = numpy.pad(
            array=waveform,
            pad_width=(0, rest_samples),
            mode="constant",
            constant_values=(offset_volts - amplitude_volts + t0_offset_volts),
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
        start_sample = int((delay_time_ms / 1000) * sampling_frequency_hz)
        fall_sample = int((fall_time_ms / 1000) * sampling_frequency_hz)
        waveform[start_sample:fall_sample] = max_volts

        repeat_number = numpy.floor(period_samples / waveform_samples)
        if repeat:
            waveform = numpy.tile(waveform, int(repeat_number))
            print(f'repeating waveform {repeat_number} times. '
                  f'total samples is {len(waveform)} samples out of {period_samples} samples')
            waveform = numpy.pad(array=waveform,
                                 pad_width=(0, period_samples - len(waveform)),
                                 mode="constant",
                                 constant_values=min_volts)
        else:
            waveform = numpy.pad(array=waveform,
                                 pad_width=(0, period_samples - waveform_samples),
                                 mode="constant",
                                 constant_values=min_volts)

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
        time_samples_ms = numpy.linspace(
            0, 2 * numpy.pi, waveform_samples)
        waveform = offset_volts + amplitude_volts * numpy.sin(time_samples_ms)
        repeat_number = numpy.floor(period_samples / waveform_samples)
        if repeat:
            waveform = numpy.tile(waveform, int(repeat_number))
            print(f'repeating waveform {repeat_number} times. '
                  f'total samples is {len(waveform)} samples out of {period_samples} samples')
            waveform = numpy.pad(array=waveform,
                                 pad_width=(0, period_samples - len(waveform)),
                                 mode="constant",
                                 constant_values=(offset_volts))
        else:
            waveform = numpy.pad(array=waveform,
                                 pad_width=(0, period_samples - waveform_samples),
                                 mode="constant",
                                 constant_values=(offset_volts))

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
