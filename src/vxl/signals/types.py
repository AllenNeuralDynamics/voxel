"""The signal types a profile gives each net, and the edges that place a signal's window in the frame."""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Annotated, Any, Literal, Self

from pydantic import Discriminator, Field, Tag, model_validator
from vxlib.schema import FrozenModel
from vxlib.units import Angle, Percent, Quantity, Time, Voltage

from vxl.config.identifiers import NetName

type EdgeName = Literal["start", "end"]


class FrameEdge(FrozenModel):
    """An edge placed from the start or the end of the frame."""

    frame: EdgeName
    offset: Time


class SignalEdge(FrozenModel):
    """An edge placed from an edge of another signal of the same generator."""

    signal: NetName
    edge: EdgeName
    offset: Time


type Edge = FrameEdge | SignalEdge


class _Window(FrozenModel):
    start: Edge
    end: Edge


class DigitalOn(FrozenModel):
    """On for the whole frame."""

    type: Literal["on"]


class DigitalPulse(_Window):
    """On from ``start`` to ``end``."""

    type: Literal["pulse"]


class DigitalTrain(_Window):
    """``count`` pulses: pulse k turns on at start + k * (end - start) / count and stays on for ``width``."""

    type: Literal["train"]
    count: int = Field(ge=1)
    width: Time

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.width <= 0:
            raise ValueError("'width' must be greater than 0")
        return self


class Correction(FrozenModel):
    """Rows of ``[wanted, sent]`` in the net's unit, rising in both columns."""

    rows: list[tuple[Quantity, Quantity]] = Field(min_length=2)

    @model_validator(mode="before")
    @classmethod
    def _from_rows(cls, data: Any) -> Any:
        return {"rows": data} if isinstance(data, list) else data

    @model_validator(mode="after")
    def _check(self) -> Self:
        for (wanted_a, sent_a), (wanted_b, sent_b) in pairwise(self.rows):
            if not (wanted_b > wanted_a and sent_b > sent_a):
                raise ValueError("correction rows must rise in both columns")
        return self

    @property
    def values(self) -> list[Quantity]:
        return [value for row in self.rows for value in row]


class AnalogConstant(FrozenModel):
    """1 value for the whole frame."""

    type: Literal["constant"]
    value: Quantity
    correction: Correction | None = None


class AnalogPulse(_Window):
    """``active`` from ``start`` to ``end``, and ``idle`` outside. A dip has ``active`` below ``idle``."""

    type: Literal["pulse"]
    idle: Quantity
    active: Quantity
    correction: Correction | None = None


class AnalogStaircase(_Window):
    """Equal steps from ``first`` to ``last``, up or down."""

    type: Literal["staircase"]
    first: Quantity
    last: Quantity
    steps: int = Field(ge=2)
    correction: Correction | None = None


class AnalogPoints(_Window):
    """Straight lines between points, as in SPICE ``PWL``.

    Each point is ``[time, value]``: the time is a part of the window, from ``0 %`` to ``100 %``, and the value is
    in the net's unit.
    """

    type: Literal["points"]
    points: list[tuple[Percent, Quantity]] = Field(min_length=2)
    correction: Correction | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        times = [time for time, _ in self.points]
        if times[0] != 0 or times[-1] != 1:
            raise ValueError("points must start at 0 % and end at 100 %")
        if any(b < a for a, b in pairwise(times)):
            raise ValueError("point times must not go back")
        return self


class AnalogWave(_Window):
    """``cycles`` periods of a shape from center - amplitude to center + amplitude.

    ``split`` is the part of each period spent rising, so ``split: 1`` is a sawtooth.
    """

    type: Literal["wave"]
    shape: Literal["triangle", "sine", "square"]
    center: Quantity
    amplitude: Quantity
    cycles: float = Field(default=1, gt=0)
    phase: Angle = Angle.of(0.0, "deg")
    split: float = Field(default=0.5, ge=0, le=1)
    correction: Correction | None = None


class AnalogFollow(FrozenModel):
    """Another net's volts * ``scale`` + ``offset``, ``delay`` later."""

    type: Literal["follow"]
    source: NetName
    scale: float = Field(default=1, allow_inf_nan=False)
    offset: Voltage = Voltage.of(0.0, "V")
    delay: Time = Time.of(0.0, "ms")


def _signal_tag(value: Any) -> str | None:
    if isinstance(value, dict):
        kind = value.get("type")
        if kind == "pulse":
            return "analog_pulse" if {"idle", "active"} & value.keys() else "digital_pulse"
        return kind if isinstance(kind, str) else None
    if isinstance(value, AnalogPulse):
        return "analog_pulse"
    if isinstance(value, DigitalPulse):
        return "digital_pulse"
    return getattr(value, "type", None)


type DigitalSignal = DigitalOn | DigitalPulse | DigitalTrain
type AnalogSignal = AnalogConstant | AnalogPulse | AnalogStaircase | AnalogPoints | AnalogWave | AnalogFollow

type Signal = Annotated[
    Annotated[DigitalOn, Tag("on")]
    | Annotated[DigitalPulse, Tag("digital_pulse")]
    | Annotated[DigitalTrain, Tag("train")]
    | Annotated[AnalogConstant, Tag("constant")]
    | Annotated[AnalogPulse, Tag("analog_pulse")]
    | Annotated[AnalogStaircase, Tag("staircase")]
    | Annotated[AnalogPoints, Tag("points")]
    | Annotated[AnalogWave, Tag("wave")]
    | Annotated[AnalogFollow, Tag("follow")],
    Discriminator(
        _signal_tag,
        custom_error_type="signal_type",
        custom_error_message="unknown signal type; see the signal types in signals.md",
    ),
]
"""1 signal for 1 net. A ``pulse`` with ``idle`` and ``active`` is analog, and a ``pulse`` without them is digital."""

DIGITAL_TYPES: tuple[type, ...] = (DigitalOn, DigitalPulse, DigitalTrain)
ANALOG_TYPES: tuple[type, ...] = (AnalogConstant, AnalogPulse, AnalogStaircase, AnalogPoints, AnalogWave, AnalogFollow)


@dataclass(frozen=True)
class EdgeProblem:
    """A signal edge that cannot be placed."""

    signal: str
    edge: EdgeName
    reason: Literal["unknown_signal", "loop"]
    detail: str


@dataclass(frozen=True)
class Window:
    """The resolved times of a signal's edges, in seconds from the frame start."""

    start: float
    end: float


def resolve_windows(signals: Mapping[str, Any], duration: float) -> tuple[dict[str, Window], list[EdgeProblem]]:
    """Place every signal's edges in a frame of ``duration`` seconds.

    A signal without edges spans the whole frame. A ``follow`` takes its source's window, ``delay`` later.
    Signals whose edges name an unknown signal or form a loop are left out of the result and reported.
    """
    times: dict[tuple[str, EdgeName], float] = {}
    problems: list[EdgeProblem] = []
    failed: set[tuple[str, EdgeName]] = set()

    def place(name: str, edge: EdgeName, path: tuple[tuple[str, EdgeName], ...]) -> float | None:
        key = (name, edge)
        if key in times:
            return times[key]
        if key in failed:
            return None
        if key in path:
            loop = " → ".join(f"{n}.{e}" for n, e in (*path[path.index(key) :], key))
            problems.append(EdgeProblem(path[0][0], path[0][1], "loop", loop))
            failed.update(path)
            return None
        signal = signals[name]
        if isinstance(signal, AnalogFollow):
            if signal.source not in signals:
                problems.append(EdgeProblem(name, edge, "unknown_signal", signal.source))
                failed.add(key)
                return None
            base = place(signal.source, edge, (*path, key))
            value = None if base is None else base + signal.delay
        elif isinstance(signal, _Window):
            spec = signal.start if edge == "start" else signal.end
            if isinstance(spec, FrameEdge):
                value = (0.0 if spec.frame == "start" else duration) + spec.offset
            elif spec.signal not in signals:
                problems.append(EdgeProblem(name, edge, "unknown_signal", spec.signal))
                value = None
            else:
                base = place(spec.signal, spec.edge, (*path, key))
                value = None if base is None else base + spec.offset
        else:
            value = 0.0 if edge == "start" else duration
        if value is None:
            failed.add(key)
            return None
        times[key] = value
        return value

    windows: dict[str, Window] = {}
    for name in signals:
        start = place(name, "start", ())
        end = place(name, "end", ())
        if start is not None and end is not None:
            windows[name] = Window(start, end)
    return windows, problems


__all__ = [
    "ANALOG_TYPES",
    "DIGITAL_TYPES",
    "AnalogConstant",
    "AnalogFollow",
    "AnalogPoints",
    "AnalogPulse",
    "AnalogSignal",
    "AnalogStaircase",
    "AnalogWave",
    "Correction",
    "DigitalOn",
    "DigitalPulse",
    "DigitalSignal",
    "DigitalTrain",
    "Edge",
    "EdgeName",
    "EdgeProblem",
    "FrameEdge",
    "Signal",
    "SignalEdge",
    "Window",
    "resolve_windows",
]
