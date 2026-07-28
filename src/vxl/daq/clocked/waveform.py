import csv
from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, TypeAdapter, model_validator
from vxlib.quantity import Angle, Frequency, NormalizedRange, Time, Voltage, VoltageRange


class BaseWaveform(BaseModel, ABC):
    model_config = ConfigDict(extra="forbid")

    voltage: VoltageRange
    window: NormalizedRange
    rest_voltage: Voltage = Voltage(0.0)

    @model_validator(mode="after")
    def clamp_rest_voltage(self) -> Self:
        self.rest_voltage = Voltage(max(self.voltage.min, min(self.voltage.max, float(self.rest_voltage))))
        return self

    def get_array(self, total_samples: int) -> np.ndarray:
        """Generate the waveform array, ending on the configured rest voltage."""
        if total_samples < 1:
            raise ValueError("Waveforms require at least one sample")

        arr = np.full(total_samples, float(self.rest_voltage))
        start_idx = int(self.window.min * total_samples)
        end_idx = int(self.window.max * total_samples)
        n = end_idx - start_idx
        if n > 0:
            arr[start_idx:end_idx] = self._generate_waveform(n)
        arr[-1] = float(self.rest_voltage)
        return arr

    @abstractmethod
    def _generate_waveform(self, n: int) -> np.ndarray:
        """Generate N samples covering exactly [window.min, window.max)."""


class PeriodicWaveform(BaseWaveform, ABC):
    """Base for waveforms that repeat a configured number of cycles.

    Integer values complete whole cycles within the active window; fractional
    values intentionally end at an intermediate phase.
    """

    cycles: float = Field(default=1.0, gt=0)
    phase: Angle = Angle(0.0)

    def _phase_array(self, n: int) -> np.ndarray:
        """Generate normalized phase for ``cycles`` across ``n`` samples."""
        if n < 1:
            return np.zeros(n)
        phase_offset = float(self.phase) / (2 * np.pi)
        return (np.arange(n) * self.cycles / n + phase_offset) % 1.0


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
        phi = self._phase_array(n)
        shape = np.sin(2 * np.pi * phi)
        return (shape + 1) / 2 * (self.voltage.max - self.voltage.min) + self.voltage.min


class TriangleWave(PeriodicWaveform):
    """Sawtooth/triangle waveform. `symmetry` controls rise/fall ratio:
    1.0 = pure ramp up, 0.0 = pure ramp down, 0.5 = symmetric triangle.
    """

    type: Literal["triangle", "sawtooth"]
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


def generate_multi_point_waveform(n: int, points: list[list[float]], voltage_range: VoltageRange) -> np.ndarray:
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


# ==================== Derived Waveforms ====================


class _DerivedBase(BaseModel, ABC):
    """Shared fields for waveforms derived from another channel.

    Resolution happens at controller load-time by looking up ``source`` among
    sibling waveforms and applying the operation to its resolved samples.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["derived"] = "derived"
    source: str

    @abstractmethod
    def apply(self, src_array: np.ndarray) -> np.ndarray: ...


class DerivedMirror(_DerivedBase):
    """Reflect the source voltage around ``about``. Push-pull / differential pair."""

    operation: Literal["mirror"] = "mirror"
    about: Voltage = Voltage(0.0)

    def apply(self, src_array: np.ndarray) -> np.ndarray:
        return 2.0 * float(self.about) - src_array


class DerivedScale(_DerivedBase):
    """Scale the source voltage around ``about`` by ``factor``."""

    operation: Literal["scale"] = "scale"
    factor: float
    about: Voltage = Voltage(0.0)

    def apply(self, src_array: np.ndarray) -> np.ndarray:
        about = float(self.about)
        return about + self.factor * (src_array - about)


class DerivedOffset(_DerivedBase):
    """Add a constant ``delta`` to the source's voltage values."""

    operation: Literal["offset"] = "offset"
    delta: Voltage

    def apply(self, src_array: np.ndarray) -> np.ndarray:
        return src_array + self.delta


class DerivedShift(_DerivedBase):
    """Time-shift the source by ``fraction`` of the cycle (0-1).

    For periodic sources this is equivalent to a phase offset.
    """

    operation: Literal["shift"] = "shift"
    fraction: float = Field(ge=0.0, le=1.0)

    def apply(self, src_array: np.ndarray) -> np.ndarray:
        n = len(src_array)
        if n < 1:
            raise ValueError("Derived waveforms require at least one source sample")
        rest_voltage = src_array[-1]
        shift_samples = round(self.fraction * n) % n
        shifted = np.roll(src_array, shift_samples)
        shifted[-1] = rest_voltage
        return shifted


def _waveform_discriminator(v: Any) -> str | None:
    """Map a Waveform payload to a discriminator tag.

    For ``type: derived`` variants, tag on ``type + operation`` so each derived
    subclass picks up its own fields. For plain primitives, tag on ``type``.
    """
    if isinstance(v, dict):
        t = v.get("type")
        if t == "derived":
            op = v.get("operation")
            return f"derived:{op}" if op else None
        return t
    t = getattr(v, "type", None)
    if t == "derived":
        op = getattr(v, "operation", None)
        return f"derived:{op}" if op else None
    return t


Waveform = Annotated[
    Annotated[SquareWave, Tag("square")]
    | Annotated[SineWave, Tag("sine")]
    | Annotated[TriangleWave, Tag("triangle")]
    | Annotated[TriangleWave, Tag("sawtooth")]
    | Annotated[MultiPointWaveform, Tag("multi_point")]
    | Annotated[PulseWaveform, Tag("pulse")]
    | Annotated[CSVWaveform, Tag("csv")]
    | Annotated[DerivedMirror, Tag("derived:mirror")]
    | Annotated[DerivedScale, Tag("derived:scale")]
    | Annotated[DerivedOffset, Tag("derived:offset")]
    | Annotated[DerivedShift, Tag("derived:shift")],
    Discriminator(_waveform_discriminator),
]

_WaveformAdapter = TypeAdapter(Waveform)


def validate_waveform(data: dict) -> Waveform:
    """Validate a single waveform dict into the appropriate Waveform subtype."""
    return _WaveformAdapter.validate_python(data)


class TransitionPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["transitions"] = "transitions"
    start: bool = False
    rest: bool = False
    transitions: tuple[float, ...] = ()


DigitalPattern = TransitionPattern


def _topo_order(waveforms: Mapping[str, Waveform]) -> list[str]:
    """Return waveform keys in dependency order (sources before derived).

    Raises ``WaveformResolutionError`` on missing sources or cycles.
    """
    unresolved: list[str] = []
    for name, wf in waveforms.items():
        if isinstance(wf, _DerivedBase):
            if wf.source not in waveforms:
                raise WaveformResolutionError(f"Derived waveform '{name}' references unknown source '{wf.source}'")
            unresolved.append(name)

    order: list[str] = [name for name, wf in waveforms.items() if not isinstance(wf, _DerivedBase)]
    resolved: set[str] = set(order)

    while unresolved:
        made_progress = False
        still_unresolved: list[str] = []
        for name in unresolved:
            wf = waveforms[name]
            if not isinstance(wf, _DerivedBase):
                continue
            if wf.source in resolved:
                order.append(name)
                resolved.add(name)
                made_progress = True
            else:
                still_unresolved.append(name)
        if not made_progress:
            raise WaveformResolutionError(
                f"Cycle or unresolvable source among derived waveforms: {sorted(still_unresolved)}"
            )
        unresolved = still_unresolved

    return order


class WaveformResolutionError(ValueError):
    """Raised when derived waveforms cannot be resolved (missing source / cycle)."""


class Signals(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_rate: Frequency = Field(..., gt=0)
    duration: Time = Field(..., gt=0)
    rest_time: Time = Field(default=Time(0.0), ge=0)
    waveforms: dict[str, Waveform]

    @model_validator(mode="after")
    def at_least_one_sample(self) -> "Signals":
        if self.num_samples < 1:
            raise ValueError("num_samples must be at least 1")
        return self

    @property
    def num_samples(self) -> int:
        """Total AO samples per cycle (duration * sample_rate, floor)."""
        return int(float(self.sample_rate) * float(self.duration))

    @property
    def frame_frequency(self) -> float:
        """Cycle frequency: 1 / (duration + rest_time). Zero when total span is zero."""
        total = float(self.duration) + float(self.rest_time)
        return 1.0 / total if total > 0 else 0.0

    def arrays(self, voltage_range: VoltageRange | None = None) -> dict[str, np.ndarray]:
        """Resolve ``self.waveforms`` to sample arrays at this config's ``num_samples``.

        Raises ``WaveformResolutionError`` on cycles or missing sources among derived
        waveforms.
        """
        arrays: dict[str, np.ndarray] = {}
        for name in _topo_order(self.waveforms):
            waveform = self.waveforms[name]
            if isinstance(waveform, BaseWaveform):
                arrays[name] = waveform.get_array(self.num_samples)
            elif isinstance(waveform, _DerivedBase):
                arrays[name] = waveform.apply(arrays[waveform.source])
            else:
                raise WaveformResolutionError(f"Unknown waveform type for '{name}': {type(waveform).__name__}")

        errors: list[str] = []
        for name, array in arrays.items():
            if not np.all(np.isfinite(array)):
                errors.append(f"non-finite values in array for {name}")
            minimum = float(np.min(array))
            maximum = float(np.max(array))
            if voltage_range is not None and (minimum < voltage_range.min or maximum > voltage_range.max):
                errors.append(f"values out of range for {name}")
        if errors:
            raise WaveformResolutionError("\n".join(errors))
        return arrays
