import csv
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Annotated, Literal, Self

import numpy as np
from pydantic import BaseModel, Discriminator, Field, TypeAdapter, model_validator
from vxlib.quantity import Angle, Frequency, NormalizedRange, Voltage, VoltageRange


class BaseWaveform(BaseModel, ABC):
    voltage: VoltageRange
    window: NormalizedRange
    rest_voltage: Voltage = Voltage(0.0)

    @model_validator(mode="after")
    def clamp_rest_voltage(self) -> Self:
        self.rest_voltage = Voltage(max(self.voltage.min, min(self.voltage.max, float(self.rest_voltage))))
        return self

    def get_array(self, total_samples: int) -> np.ndarray:
        """Generate the waveform array for the entire task duration."""
        arr = np.full(total_samples, float(self.rest_voltage))
        start_idx = int(self.window.min * total_samples)
        end_idx = int(self.window.max * total_samples)
        n = end_idx - start_idx
        if n <= 0:
            return arr

        waveform_segment = self._generate_waveform(n)

        arr[start_idx:end_idx] = waveform_segment
        return arr

    @abstractmethod
    def _generate_waveform(self, n: int) -> np.ndarray:
        """Generate N samples covering exactly [window.min, window.max)."""


class PeriodicWaveform(BaseWaveform, ABC):
    """Base for waveforms with frequency/cycles periodicity.

    Specify either `cycles` (integer, guarantees clean periodicity) or
    `frequency` (Hz, for exact frequency control). If both are set,
    `cycles` takes precedence. Defaults to 1 cycle if neither is set.
    """

    frequency: Frequency | None = None
    cycles: int | None = None
    phase: Angle = Angle(0.0)

    @property
    def effective_frequency(self) -> float:
        """Resolve frequency from cycles or direct frequency setting."""
        span = self.window.span
        if self.cycles is not None:
            return self.cycles / span if span > 0 else 0
        if self.frequency is not None:
            return float(self.frequency)
        return 1 / span if span > 0 else 0

    def _effective_sample_rate(self, n: int) -> float:
        """Compute the effective sample rate for the windowed segment."""
        span = self.window.span
        return n / span if span > 0 else 0

    def _phase_array(self, n: int) -> np.ndarray:
        """Generate a normalized phase array [0..1) repeating at effective_frequency."""
        fs = self._effective_sample_rate(n)
        if fs <= 0:
            return np.zeros(n)
        t = np.arange(n) / fs
        phase_offset = self.phase / (2 * np.pi)
        return (t * self.effective_frequency + phase_offset) % 1.0


class SquareWave(PeriodicWaveform):
    type: Literal["square"]
    duty_cycle: float

    def _generate_waveform(self, n: int) -> np.ndarray:
        if self.window.span == 0:
            return np.array([])
        phi = self._phase_array(n)
        return np.where(phi < self.duty_cycle, self.voltage.max, self.voltage.min)


class SineWave(PeriodicWaveform):
    type: Literal["sine"]

    def _generate_waveform(self, n: int) -> np.ndarray:
        if self.window.span == 0:
            return np.array([])
        # Sine uses phase directly in the sin() call rather than _phase_array
        fs = self._effective_sample_rate(n)
        t = np.arange(n) / fs
        shape = np.sin(2 * np.pi * self.effective_frequency * t + self.phase)
        return (shape + 1) / 2 * (self.voltage.max - self.voltage.min) + self.voltage.min


class SawtoothWave(PeriodicWaveform):
    """Sawtooth/triangle waveform. `symmetry` controls rise/fall ratio:
    1.0 = pure ramp up, 0.0 = pure ramp down, 0.5 = symmetric triangle.
    """

    type: Literal["sawtooth"]
    symmetry: float = 1.0

    def _generate_waveform(self, n: int) -> np.ndarray:
        if self.window.span == 0:
            return np.array([])
        phi = self._phase_array(n)
        raw = np.where(
            phi < self.symmetry,
            2 * phi / max(self.symmetry, 1e-6) - 1,
            1 - 2 * (phi - self.symmetry) / (1 - self.symmetry) if (1 - self.symmetry) != 0 else -1,
        )
        return (raw + 1) / 2 * (self.voltage.max - self.voltage.min) + self.voltage.min


def generate_multi_point_waveform(
    n: int,
    points: list[list[float]],
    voltage_range: VoltageRange,
) -> np.ndarray:
    """Generate a waveform by interpolating between a series of normalized time-voltage points.

    :param n: Number of samples to generate.
    :param points: List of [time, voltage] points, both normalized to [0.0, 1.0].
    :param voltage_range: Voltage range to scale the output waveform.
    :return: np.ndarray: Array of waveform samples scaled to the specified voltage range.

    """
    t_interp = np.linspace(0, 1, n, endpoint=False, retstep=False)

    # Unzip points for interpolation
    t_points, v_points_norm = zip(*points, strict=True)

    # Interpolate the normalized shape
    v_interp_norm = np.interp(t_interp, t_points, v_points_norm)

    # Scale to the final voltage range
    return v_interp_norm * (voltage_range.max - voltage_range.min) + voltage_range.min


class MultiPointWaveform(BaseWaveform):
    """A flexible waveform defined by a series of normalized time-voltage points."""

    type: Literal["multi_point"]
    points: list[list[float]] = Field(..., description="List of [time, voltage] points, normalized from 0.0 to 1.0.")

    @model_validator(mode="after")
    def check_points(self) -> "MultiPointWaveform":
        if not self.points:
            err = "MultiPointWaveform must have at least one point."
            raise ValueError(err)
        for p in self.points:
            if not (0.0 <= p[0] <= 1.0 and 0.0 <= p[1] <= 1.0):
                err = f"All points must be normalized between 0.0 and 1.0. Found: {p}"
                raise ValueError(err)
        return self

    def _generate_waveform(self, n: int) -> np.ndarray:
        return generate_multi_point_waveform(n, self.points, self.voltage)


class PulseWaveform(BaseWaveform):
    """A trapezoidal pulse defined by a start and end time for its peak voltage."""

    type: Literal["pulse"]

    def _generate_waveform(self, n: int) -> np.ndarray:
        points = [[self.window.min, 1.0], [self.window.max, 1.0]]
        return generate_multi_point_waveform(n=n, points=points, voltage_range=self.voltage)


class CSVWaveform(BaseWaveform):
    """A waveform defined by a CSV file containing time-voltage pairs."""

    type: Literal["csv"]
    csv_file: str = Field(..., description="Path to the CSV file containing time-voltage pairs.")
    directory: str | None = None

    _points: list[list[float]] | None = None

    @model_validator(mode="after")
    def load_csv_points(self) -> "CSVWaveform":
        self._points = self._load_points()
        return self

    def _resolve_csv_path(self) -> Path:
        csv_path = Path(self.csv_file)
        if not csv_path.is_absolute() and self.directory:
            csv_path = Path(self.directory) / csv_path
        if not csv_path.exists():
            err_msg = f"CSV file not found: {csv_path}, directory: {self.directory}"
            raise FileNotFoundError(err_msg)
        return csv_path

    def _load_points(self) -> list[list[float]]:
        points = []
        csv_path = self._resolve_csv_path()
        with csv_path.open(newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                # Skip header if present (non-numeric values)
                try:
                    t, v = map(float, row)
                except ValueError:
                    continue
                points.append([t, v])
        return points

    def _generate_waveform(self, n: int) -> np.ndarray:
        if self._points is None:
            self._points = self._load_points()

        return generate_multi_point_waveform(n=n, points=self._points, voltage_range=self.voltage)


Waveform = Annotated[
    SquareWave | SineWave | SawtoothWave | MultiPointWaveform | PulseWaveform | CSVWaveform,
    Discriminator("type"),
]

_WaveformAdapter = TypeAdapter(Waveform)


def validate_waveform(data: dict) -> Waveform:
    """Validate a single waveform dict into the appropriate Waveform subtype."""
    return _WaveformAdapter.validate_python(data)
