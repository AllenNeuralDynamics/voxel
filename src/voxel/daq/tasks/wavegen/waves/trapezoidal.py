import numpy as np
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from scipy import signal

from voxel.utils.descriptors.deliminated import deliminated_property
from voxel.utils.log_config import get_component_logger

from .base import WaveformData, WaveGenTiming


class TrapezoidalWave:
    """A class to generate waveforms for the DAQ."""

    def __init__(
        self,
        name: str,
        timing: "WaveGenTiming",
        min_voltage_limit: float,
        max_voltage_limit: float,
        min_voltage: float | None = None,
        max_voltage: float | None = None,
        rise_point: float = 0.0,
        high_point: float = 0.5,
        fall_point: float = 0.5,
        low_point: float = 1.0,
        is_digital: bool = True,
        apply_filter: bool | None = False,
    ) -> None:
        self.name = name
        self.log = get_component_logger(self)
        self.timing = timing
        self.min_voltage_limit = min_voltage_limit
        self.max_voltage_limit = max_voltage_limit

        self.is_digital = is_digital
        self._filter = apply_filter if apply_filter is not None else not is_digital
        self._filter_order = 3
        self._lowpass_cutoff = self.timing.sampling_rate / 10

        self._max_voltage = max_voltage if max_voltage else self.max_voltage_limit
        self._min_voltage = min_voltage if min_voltage else self.min_voltage_limit
        self._rise_point = rise_point
        self._high_point = high_point if not is_digital else rise_point
        self._fall_point = fall_point
        self._low_point = low_point if not is_digital else fall_point

        self.rise_point = self.rise_point  # trigger validation
        self.data = self._generate()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}[{self.name}] \n"
            f"  timing={self.timing} \n"
            f"  voltage={self.min_voltage}, {self.max_voltage}\n"
            f"  waveform={self.rise_point} - {self.high_point} - {self.fall_point} - {self.low_point})"
        )

    @deliminated_property(
        minimum=lambda self: self.min_voltage,
        maximum=lambda self: self.max_voltage_limit,
        unit="V",
        description="The maximum voltage of the waveform.",
    )
    def max_voltage(self) -> float:
        return self._max_voltage

    @max_voltage.setter
    def max_voltage(self, voltage: float) -> None:
        self._max_voltage = voltage

    @deliminated_property(
        minimum=lambda self: self.min_voltage_limit,
        maximum=lambda self: self.max_voltage,
        unit="V",
        description="The minimum voltage of the waveform.",
    )
    def min_voltage(self) -> float:
        return self._min_voltage

    @min_voltage.setter
    def min_voltage(self, voltage: float) -> None:
        self._min_voltage = voltage

    @property
    def amplitude(self) -> float:
        return (self.max_voltage - self.min_voltage) / 2

    @property
    def apply_filter(self) -> bool:
        return self._filter

    @apply_filter.setter
    def apply_filter(self, apply: bool) -> None:
        self._filter = apply
        self.regenerate()

    @property
    def lowpass_filter_order(self) -> int:
        return self._filter_order

    @lowpass_filter_order.setter
    def lowpass_filter_order(self, order: int) -> None:
        self._filter_order = order
        if self.apply_filter:
            self.regenerate()

    @deliminated_property(
        minimum=0.0,
        maximum=lambda self: self.timing.sample_rate / 2,
        unit="Hz",
        description="The cutoff frequency for a lowpass filter to smooth out the waveform.",
    )
    def lowpass_cutoff(self) -> float:
        return self._lowpass_cutoff

    @lowpass_cutoff.setter
    def lowpass_cutoff(self, cutoff_frequency: float) -> None:
        self._lowpass_cutoff = cutoff_frequency

    @deliminated_property(
        minimum=0.0,
        maximum=1.0,
        unit="fraction",
        description="The point in the waveform where the rise begins.",
    )
    def rise_point(self) -> float:
        return self._rise_point

    @deliminated_property(
        minimum=lambda self: self.rise_point,
        maximum=lambda self: self.fall_point,
        unit="fraction",
        description="The point in the waveform where the maximum value is reached.",
    )
    def high_point(self) -> float:
        return self._high_point

    @deliminated_property(
        minimum=lambda self: self.high_point,
        maximum=lambda self: self.low_point,
        unit="fraction",
        description="The point in the waveform where the fall begins.",
    )
    def fall_point(self) -> float:
        return self._fall_point

    @deliminated_property(
        minimum=lambda self: self.fall_point,
        maximum=1.0,
        unit="fraction",
        description="The point in the waveform where the minimum value is reached.",
    )
    def low_point(self) -> float:
        return self._low_point

    @rise_point.setter
    def rise_point(self, point: float) -> None:
        self._rise_point = point
        if self.is_digital and self.rise_point != self.high_point:
            self.high_point = self.rise_point
        self.high_point = self.high_point

    @high_point.setter
    def high_point(self, point: float) -> None:
        self._high_point = point
        if self.is_digital and self.high_point != self.rise_point:
            self.rise_point = self.high_point
        self.fall_point = self.fall_point

    @fall_point.setter
    def fall_point(self, point: float) -> None:
        self._fall_point = point
        if self.is_digital and self.fall_point != self.low_point:
            self.low_point = self.fall_point
        self.low_point = self.low_point

    @low_point.setter
    def low_point(self, point: float) -> None:
        self._low_point = point
        if self.is_digital and self.low_point != self.fall_point:
            self.fall_point = self.low_point
        self.regenerate()

    def regenerate(self) -> None:
        self.data = self._generate()

    def _generate(self) -> WaveformData:
        samples = self.timing.samples_per_period
        waveform = np.full(samples, self.min_voltage)
        rise_point = int(samples * self.rise_point)
        high_point = int(samples * self.high_point)
        fall_point = int(samples * self.fall_point)
        low_point = int(samples * self.low_point)
        waveform[rise_point:high_point] = np.linspace(self.min_voltage, self.max_voltage, high_point - rise_point)
        waveform[high_point:fall_point] = self.max_voltage
        waveform[fall_point:low_point] = np.linspace(self.max_voltage, self.min_voltage, low_point - fall_point)
        if self.apply_filter:
            waveform = self._apply_lowpass_filter(
                waveform, self.lowpass_cutoff, self.timing.sampling_rate, self.lowpass_filter_order
            )

        return waveform

    @staticmethod
    def _apply_lowpass_filter(waveform: WaveformData, cutoff: float, sample_rate: float, order: int) -> WaveformData:
        if cutoff == 0:
            return waveform
        samples = len(waveform)
        nyquist_frequency = sample_rate / 2
        normalized_cutoff_frequency = cutoff / nyquist_frequency
        sos = signal.bessel(order, normalized_cutoff_frequency, output="sos")
        extended_waveform = np.tile(waveform, 3)
        filtered_waveform = signal.sosfiltfilt(sos, extended_waveform)
        middle_range_end = samples * 2
        return filtered_waveform[samples:middle_range_end]

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

        period_ms = self.timing.period_ms

        # Plot period markers
        for i in range(periods + 1):
            ax.axvline(i * period_ms, color="gray", linestyle="--", alpha=0.5)

        # Plot waveform
        full_waveform = np.tile(self.data, periods)
        time = np.linspace(0, periods * period_ms, len(full_waveform))
        ax.plot(time, full_waveform, color=color, label=self.name, alpha=0.5)

        # Plot voltage reference lines
        voltages = [self.max_voltage, self.min_voltage, (self.max_voltage + self.min_voltage) / 2]
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

    # def plot2(self, ax: Axes | None = None, color="blue", *, periods: int = 2) -> Axes | None:
    #     show = True if ax is None else False
    #     if show:
    #         plt.figure()
    #         ax = plt.gca()
    #     period_ms = self.timing.period_ms
    #     # add a vertical markers for each period
    #     for i in range(periods + 1):
    #         ax.axvline(i * period_ms, color="gray", linestyle="--", alpha=0.5)

    #     # Plot waveform
    #     full_waveform = np.tile(self.data, periods)
    #     time = np.linspace(0, periods * period_ms, len(full_waveform))
    #     ax.plot(time, full_waveform, color=color, label=self.name, alpha=0.5)
    #     # add horizontal markers for min, max, and average voltage
    #     ax.axhline(self.max_voltage, color="teal", linestyle="--", alpha=0.5)
    #     ax.axhline(self.min_voltage, color="teal", linestyle="--", alpha=0.5)
    #     ax.axhline((self.max_voltage + self.min_voltage) / 2, color="teal", linestyle="--", alpha=0.5)
    #     if not show:
    #         return ax
    #     plt.show()


# Example usage
if __name__ == "__main__":
    timing = WaveGenTiming(sampling_rate=1e6, period_ms=500)
    wv = TrapezoidalWave(name="TestGenerator", timing=timing, min_voltage_limit=-1, max_voltage_limit=1)
    print(wv)
    wv.plot()
