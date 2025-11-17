import csv
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, model_validator

from .quantity import Angle, Frequency, NormalizedRange, Voltage, VoltageRange


class BaseWaveform(BaseModel, ABC):
    voltage: VoltageRange
    window: NormalizedRange
    rest_voltage: Voltage = Voltage(0.0)

    def get_array(self, total_samples: int) -> np.ndarray:
        """Generate the waveform array for the entire task duration."""
        arr = np.zeros(total_samples, float)
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


class SquareWave(BaseWaveform):
    type: Literal["square"]
    duty_cycle: float
    cycles: int | None = None
    frequency: Frequency | None = None

    def _generate_waveform(self, n: int) -> np.ndarray:
        if self.window.span == 0:
            return np.array([])

        # Determine the effective frequency for the window.
        if self.frequency is not None:
            freq = self.frequency
        else:
            num_cycles = self.cycles or 1
            freq = num_cycles / self.window.span

        # Calculate the effective sample rate for this segment.
        fs = n / self.window.span

        # Generate the waveform using a time vector and modulo arithmetic,
        # which is more precise than tiling.
        t = np.arange(n) / fs
        phi = (t * freq) % 1.0

        return np.where(phi < self.duty_cycle, self.voltage.max, self.voltage.min)


class SineWave(BaseWaveform):
    type: Literal["sine"]
    frequency: Frequency
    phase: Angle = Angle(0.0)  # radians

    def _generate_waveform(self, n: int) -> np.ndarray:
        window_duration = self.window.max - self.window.min
        if window_duration == 0:
            return np.array([])
        # Calculate the effective sample rate for this specific window segment.
        fs = n / window_duration

        t = np.arange(n) / fs
        shape_normalized = np.sin(2 * np.pi * self.frequency * t + self.phase)
        return (shape_normalized + 1) / 2 * (self.voltage.max - self.voltage.min) + self.voltage.min


class TriangleWave(BaseWaveform):
    type: Literal["triangle"]
    frequency: Frequency
    symmetry: float = 0.5

    def _generate_waveform(self, n: int) -> np.ndarray:
        window_duration = self.window.max - self.window.min
        if window_duration == 0:
            return np.array([])
        # Calculate the effective sample rate for this specific window segment.
        fs = n / window_duration

        t = np.arange(n) / fs
        phi = (t * float(self.frequency)) % 1.0
        raw = np.where(phi < self.symmetry, 2 * phi / self.symmetry - 1, 2 * (1 - phi) / (1 - self.symmetry) - 1)
        return (raw + 1) / 2 * (self.voltage.max - self.voltage.min) + self.voltage.min


class SawtoothWave(BaseWaveform):
    type: Literal["sawtooth"]
    frequency: Frequency
    width: float = 1.0

    def _generate_waveform(self, n: int) -> np.ndarray:
        window_duration = self.window.max - self.window.min
        if window_duration == 0:
            return np.array([])
        # Calculate the effective sample rate for this specific window segment.
        fs = n / window_duration

        t = np.arange(n) / fs
        phi = (t * float(self.frequency)) % 1.0
        raw = np.where(
            phi < self.width,
            2 * phi / self.width - 1,
            -1 + 2 * (phi - self.width) / (1 - self.width) if (1 - self.width) != 0 else -1,
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


Waveform = SquareWave | SineWave | TriangleWave | SawtoothWave | MultiPointWaveform | PulseWaveform | CSVWaveform
