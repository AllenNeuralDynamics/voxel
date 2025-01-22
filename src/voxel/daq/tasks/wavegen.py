from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from nidaqmx.constants import AcquisitionType as NiAcqType
from nidaqmx.task.channels import AOChannel as NiAOChannel
from scipy import signal

from voxel.utils.descriptors.deliminated import deliminated_float, deliminated_int

from ..daq import PinInfo, VoxelDaqTask
from .clockgen import ClockGenTask

if TYPE_CHECKING:
    from ..daq import VoxelDaq


@dataclass
class TrapezoidalWaveAnchors:
    """Anchor points for a waveform."""

    rise: float
    high: float
    fall: float
    low: float

    def __post_init__(self):
        self.rise = min(max(self.rise, 0), 1)
        self.high = min(max(self.high, 0), 1)
        self.fall = min(max(self.fall, 0), 1)
        self.low = min(max(self.low, 0), 1)


def parse_anchors(anchors: list[float]) -> list[float]:
    """Parse a list of anchor points into a TrapezoidalWaveAnchors object.
    :param anchors: A list of anchor points in the order [rise, high, fall, low].
    :type anchors: list[float]
    :return: A list of anchor points in the order [rise, high, fall, low].
    :rtype: list[float]
    """
    # sort the list in ascending order and ensure all values are between 0 and 1 then take the first 4
    anchors = sorted([min(max(anchor, 0), 1) for anchor in anchors])[:4]
    if len(anchors) == 0:
        return [0.25, 0.25, 0.75, 0.75]
    if len(anchors) == 1:
        return [anchors[0], anchors[0], anchors[0], anchors[0]]
    if len(anchors) == 2:
        return [anchors[0], anchors[0], anchors[1], anchors[1]]
    if len(anchors) == 3:
        return [anchors[0], anchors[1], anchors[1], anchors[2]]
    return anchors


class WaveAnchors(list[float]):
    def __init__(self, initial_values: list[float], on_change_callback):
        super().__init__(parse_anchors(initial_values))
        self._on_change_callback = on_change_callback

    def __setitem__(self, index, value):
        prev = 0.0
        next = 1.0
        if index in [1, 2, 3]:
            prev = self[index - 1]
        if index in [0, 1, 2]:
            next = self[index + 1]

        value = min(max(value, prev), next)
        super().__setitem__(index, value)

        self._on_change_callback()

    @property
    def rise(self) -> float:
        return self[0]

    @rise.setter
    def rise(self, value: float) -> None:
        self[0] = value

    @property
    def high(self) -> float:
        return self[1]

    @high.setter
    def high(self, value: float) -> None:
        self[1] = value

    @property
    def fall(self) -> float:
        return self[2]

    @fall.setter
    def fall(self, value: float) -> None:
        self[2] = value

    @property
    def low(self) -> float:
        return self[3]

    @low.setter
    def low(self, value: float) -> None:
        self[3] = value


class WaveGenChannel:
    def __init__(self, name: str, task: "WaveGenTask", inst: NiAOChannel):
        self.name = name
        self.task = task
        self.inst = inst

        self._apply_filter = False
        self._filter_order = 2
        self._lowpass_cutoff = self.task.sampling_rate / 2

        self._trough_voltage = task.daq.min_ao_voltage
        self._peak_voltage = task.daq.max_ao_voltage
        self._anchors = WaveAnchors([0.0, 0.0, 0.5, 0.5], self.regenerate_waveform)

        self.data = self._generate_waveform()

    @deliminated_float(min_value=lambda self: self.task.daq.min_ao_voltage, max_value=lambda self: self._peak_voltage)
    def peak_voltage(self) -> float:
        return self._peak_voltage

    @peak_voltage.setter
    def peak_voltage(self, voltage: float) -> None:
        self._peak_voltage = voltage
        self.regenerate_waveform()

    @deliminated_float(min_value=lambda self: self._trough_voltage, max_value=lambda self: self.task.daq.max_ao_voltage)
    def trough_voltage(self) -> float:
        return self._trough_voltage

    @trough_voltage.setter
    def trough_voltage(self, voltage: float) -> None:
        self._trough_voltage = voltage
        self.regenerate_waveform()

    @property
    def amplitude(self) -> float:
        return (self.peak_voltage - self.trough_voltage) / 2

    @property
    def apply_filter(self) -> bool:
        return self._apply_filter

    @deliminated_int(min_value=0, max_value=6)
    def lowpass_filter_order(self) -> int:
        return self._filter_order

    @lowpass_filter_order.setter
    def lowpass_filter_order(self, order: int) -> None:
        self._filter_order = order
        self.regenerate_waveform() if self.apply_filter else None

    @deliminated_float(min_value=0.0, max_value=lambda self: self.timing.sample_rate / 2)
    def lowpass_cutoff(self) -> float:
        return self._lowpass_cutoff

    @lowpass_cutoff.setter
    def lowpass_cutoff(self, cutoff_frequency: float) -> None:
        self._lowpass_cutoff = cutoff_frequency
        self.regenerate_waveform() if self.apply_filter else None

    @property
    def anchors(self) -> list[float]:
        return self._anchors

    @anchors.setter
    def anchors(self, anchors: list[float]) -> None:
        self._anchors = WaveAnchors(anchors, self.regenerate_waveform)

    def update_anchors(
        self,
        *,
        rise: float | None = None,
        high: float | None = None,
        fall: float | None = None,
        low: float | None = None,
    ) -> None:
        for index, value in enumerate([rise, high, fall, low]):
            if value is not None:
                self.anchors[index] = value

    def regenerate_waveform(self):
        self.data = self._generate_waveform()

    def get_downsampled_waveform(self, *, factor: int | None = None, num_samples: int | None = None) -> np.ndarray:
        """Downsample the waveform by a factor of n."""
        if factor is None and num_samples and num_samples > 0:
            factor = max(1, len(self.data) // num_samples)

        return self.data[::factor] if factor else self.data

    def plot(self, ax: Axes | None = None, color="blue", *, periods: int = 2) -> Axes:
        """
        Plot the waveform either on a new figure or an existing axes.

        :param ax: Optional matplotlib axes to plot on. If None, creates new figure
        :param color: Color of the waveform
        :param periods: Number of periods to display
        :return: The matplotlib axes object containing the plot
        """
        # Create new figure if no axes provided
        created_new_figure = False
        if ax is None:
            _, ax = plt.subplots()
            created_new_figure = True

        period_ms = self.task.period_ms

        # Plot period markers
        for i in range(periods + 1):
            ax.axvline(i * period_ms, color="gray", linestyle="--", alpha=0.5)

        # Plot waveform
        full_waveform = np.tile(self.data, periods)
        time = np.linspace(0, periods * period_ms, len(full_waveform))
        ax.plot(time, full_waveform, color=color, label=self.name, alpha=0.5)

        # Plot voltage reference lines
        voltages = [self.peak_voltage, self.trough_voltage, (self.peak_voltage + self.trough_voltage) / 2]
        for voltage in voltages:
            ax.axhline(voltage, color="teal", linestyle="--", alpha=0.5)

        # Add legend if there are labeled plots
        if ax.get_legend_handles_labels()[0]:
            ax.legend()

        # Show only if we created a new figure
        if created_new_figure:
            plt.show(block=False)
            plt.pause(0.1)  # Allow the plot to render

        return ax

    def _generate_waveform(self) -> np.ndarray:
        """Generate a trapezoidal waveform."""
        samples = int(self.task.sampling_rate * self.task.period_ms / 1000)
        waveform = np.full(shape=samples, fill_value=self.trough_voltage)
        rise_point = int(samples * self.anchors[0])
        high_point = int(samples * self.anchors[1])
        fall_point = int(samples * self.anchors[2])
        low_point = int(samples * self.anchors[3])

        waveform[rise_point:high_point] = np.linspace(self.trough_voltage, self.peak_voltage, high_point - rise_point)
        waveform[high_point:fall_point] = self.peak_voltage
        waveform[fall_point:low_point] = np.linspace(self.peak_voltage, self.trough_voltage, low_point - fall_point)

        return self._apply_lowpass_filter(waveform) if self.apply_filter else waveform

    def _apply_lowpass_filter(self, waveform: np.ndarray) -> np.ndarray:
        if self.lowpass_cutoff == 0:
            return waveform
        samples = len(waveform)
        nyquist_frequency = self.task.sampling_rate / 2
        normalized_cutoff_frequency = self.lowpass_cutoff / nyquist_frequency
        sos = signal.bessel(self.lowpass_filter_order, normalized_cutoff_frequency, output="sos")
        extended_waveform = np.tile(waveform, 3)
        filtered_waveform = signal.sosfiltfilt(sos, extended_waveform)
        middle_range_end = samples * 2
        return filtered_waveform[samples:middle_range_end]


class WaveGenTask(VoxelDaqTask):
    """A wrapper class for a nidaqmx DAQ Task managing analog and digital output channels.
    :param name: The name of the task. Also used as the task identifier in nidaqmx.
    :param daq: A reference to the Daq object.
    :param sampling_rate_hz: The sampling rate in Hz.
    :param period_ms: The period of the waveform in milliseconds.
    :param trigger_source: Optional trigger source for the task.
    :type name: str
    :type daq: Daq
    :type sampling_rate_hz: float
    :type period_ms: float
    :type trigger: ClkGenTask | None
    Note:
        - This task is designed for generating waveforms on AO and DO channels.
        - The nidaqmx Task API can still be accessed via the inst attribute.
    """

    def __init__(
        self,
        name: str,
        daq: "VoxelDaq",
        period_ms: float,
        sampling_rate_hz: int | float,
        trigger_task: ClockGenTask | None = None,
    ) -> None:
        super().__init__(name=name, daq=daq)
        self._pins: list[PinInfo] = []

        self.channels: dict[str, WaveGenChannel] = {}
        self.waveforms: np.ndarray = np.array([])

        self._period_ms = period_ms
        self._sampling_rate = sampling_rate_hz

        self.trigger_task = trigger_task
        self._sample_mode = NiAcqType.FINITE if self.trigger_task else NiAcqType.CONTINUOUS

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}[{self.name}] \n"
            f"  period={self.period_ms} ms, sampling_rate={self.sampling_rate} Hz\n"
            f"  channels={list(self.channels.keys())}"
        )

    @property
    def pins(self) -> list[PinInfo]:
        return self._pins

    @property
    def period_ms(self) -> float:
        return self._period_ms

    @period_ms.setter
    def period_ms(self, period: float) -> None:
        self._period_ms = period
        if self.channels:
            self._cfg_timing()
            self.regenerate_waveforms()

    @property
    def sampling_rate(self) -> float:
        return self.inst.timing.samp_clk_rate

    @sampling_rate.setter
    def sampling_rate(self, sample_rate: float) -> None:
        self._sampling_rate = sample_rate
        if self.channels:
            self._cfg_timing()
            self.regenerate_waveforms()

    @property
    def samples_per_period(self) -> int:
        """The number of samples per period. Determines the buffer size created for continuous tasks."""
        return int(self.sampling_rate * self.period_ms / 1000)

    def add_channel(self, name: str, pin: str) -> WaveGenChannel:
        """Add an analog output channel to the task."""
        pin: PinInfo = self.daq.assign_pin(pin)
        channel_inst = self.inst.ao_channels.add_ao_voltage_chan(pin.path, name)
        channel = WaveGenChannel(name=name, task=self, inst=channel_inst)
        self.channels[name] = channel
        self._pins.append(pin)
        self._cfg_timing()
        self._cfg_triggering()
        return self.channels[name]

    def regenerate_waveforms(self) -> None:
        self.log.debug("Regenerating waveforms for all channels...")
        for channel in self.channels.values():
            channel.regenerate_waveform()

    def write(self) -> np.ndarray:
        self.log.info("Writing waveforms to task...")
        inst_names = self.inst.channels.channel_names
        self.regenerate_waveforms()
        # data needs to be a 2D array with shape (channels, samples)
        data = np.array([self.channels[name].data for name in inst_names])
        self.log.info(f"writing {data.shape} data to {self.inst.name}")
        written_samples = self.inst.write(data)
        if written_samples != self.samples_per_period:
            self.log.warning(f"Only wrote {written_samples} samples out of {self.samples_per_period} requested.")
        return data

    def start(self) -> None:
        self.write()
        super().start()

    def _cfg_timing(self) -> None:
        self.inst.timing.cfg_samp_clk_timing(
            rate=self.sampling_rate,
            sample_mode=self._sample_mode,
            samps_per_chan=self.samples_per_period,
        )

    def _cfg_triggering(self) -> None:
        if not self.trigger_task or not self.channels:
            return
        self.inst.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source=self.daq.get_pfi_path(self.trigger_task.out)
        )
        self.inst.triggers.start_trigger.retriggerable = True
