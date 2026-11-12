"""Signals and timelines: what a signal generator plays on its wires."""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator
from vxlib.schema import FrozenModel
from vxlib.units import Angle, Frequency, Percent, Quantity, Time, Voltage
from vxlib.vector import Span

from .config import AnalogWire, DigitalWire, WireConfig, WireName
from .errors import ViolationLoc, Violations

type EdgeName = Literal["start", "end"]


class TimelineEdge(FrozenModel):
    """An edge placed from the start or the end of the timeline."""

    timeline: EdgeName
    offset: Time = Time.of(0.0, "ms")


class SignalEdge(FrozenModel):
    """An edge placed from an edge of another signal in the same timeline."""

    signal: WireName
    edge: EdgeName
    offset: Time = Time.of(0.0, "ms")


type Edge = TimelineEdge | SignalEdge


class _Windowed(FrozenModel):
    """A part of the timeline, the whole timeline by default."""

    start: Edge = TimelineEdge(timeline="start")
    end: Edge = TimelineEdge(timeline="end")


class DigitalOn(_Windowed):
    """On from ``start`` to ``end``."""

    kind: Literal["on"]


class DigitalOff(FrozenModel):
    """Off for the whole timeline."""

    kind: Literal["off"]


class Correction(FrozenModel):
    """Rows of ``[wanted, sent]`` in the wire's unit, rising in both columns."""

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
    """1 value for the whole timeline."""

    kind: Literal["constant"]
    value: Quantity
    correction: Correction | None = None


class AnalogPulse(_Windowed):
    """``active`` from ``start`` to ``end``, and ``idle`` outside. A dip has ``active`` below ``idle``."""

    kind: Literal["pulse"]
    idle: Quantity
    active: Quantity
    correction: Correction | None = None


class AnalogStaircase(_Windowed):
    """Equal steps from ``first`` to ``last``, up or down."""

    kind: Literal["staircase"]
    first: Quantity
    last: Quantity
    steps: int = Field(ge=2)
    correction: Correction | None = None


class AnalogPoints(_Windowed):
    """Straight lines between ``[time, value]`` points, as in SPICE ``PWL``. Time runs from ``0 %`` to ``100 %`` of the
    window."""

    kind: Literal["points"]
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


class AnalogWave(_Windowed):
    """``cycles`` periods of a shape around ``center``. ``split`` is the part of each period spent rising; ``1`` is a
    sawtooth."""

    kind: Literal["wave"]
    shape: Literal["triangle", "sine", "square"]
    center: Quantity
    amplitude: Quantity
    cycles: float = Field(default=1, gt=0)
    phase: Angle = Angle.of(0.0, "deg")
    split: float = Field(default=0.5, ge=0, le=1)
    correction: Correction | None = None


class AnalogFollow(FrozenModel):
    """Another wire's volts * ``scale`` + ``offset``, ``delay`` later."""

    kind: Literal["follow"]
    source: WireName
    scale: float = Field(default=1, allow_inf_nan=False)
    offset: Voltage = Voltage.of(0.0, "V")
    delay: Time = Time.of(0.0, "ms")


type Signal = Annotated[
    DigitalOn | DigitalOff | AnalogConstant | AnalogPulse | AnalogStaircase | AnalogPoints | AnalogWave | AnalogFollow,
    Field(discriminator="kind"),
]
"""1 signal for 1 wire. A digital wire takes ``on`` and ``off``; an analog wire takes the other kinds."""

_DIGITAL_KINDS = (DigitalOn, DigitalOff)


@dataclass(frozen=True)
class _EdgeProblem:
    """A signal edge that cannot be placed."""

    signal: str
    edge: EdgeName
    reason: Literal["unknown_signal", "loop"]
    detail: str


def _place_edges(signals: Mapping[str, Any], duration: float) -> tuple[dict[str, Span], list[_EdgeProblem]]:
    """Place each signal's edges in a timeline of ``duration`` seconds. A signal whose edges name an unknown signal or
    form a loop is left out and reported."""
    times: dict[tuple[str, EdgeName], float] = {}
    problems: list[_EdgeProblem] = []
    failed: set[tuple[str, EdgeName]] = set()

    def place(name: str, edge: EdgeName, path: tuple[tuple[str, EdgeName], ...]) -> float | None:
        key = (name, edge)
        if key in times:
            return times[key]
        if key in failed:
            return None
        if key in path:
            loop = " → ".join(f"{n}.{e}" for n, e in (*path[path.index(key) :], key))
            problems.append(_EdgeProblem(path[0][0], path[0][1], "loop", loop))
            failed.update(path)
            return None
        signal = signals[name]
        if isinstance(signal, AnalogFollow):
            if signal.source not in signals:
                problems.append(_EdgeProblem(name, edge, "unknown_signal", signal.source))
                failed.add(key)
                return None
            base = place(signal.source, edge, (*path, key))
            value = None if base is None else base + signal.delay
        elif isinstance(signal, _Windowed):
            spec = signal.start if edge == "start" else signal.end
            if isinstance(spec, TimelineEdge):
                value = (0.0 if spec.timeline == "start" else duration) + spec.offset
            elif spec.signal not in signals:
                problems.append(_EdgeProblem(name, edge, "unknown_signal", spec.signal))
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

    windows: dict[str, Span] = {}
    for name in signals:
        start = place(name, "start", ())
        end = place(name, "end", ())
        if start is not None and end is not None:
            windows[name] = Span(start, end)
    return windows, problems


_EDGE_TOLERANCE = 1e-12


class Timeline(FrozenModel):
    """What 1 signal generator plays on each tick, with 1 signal for each wire it plays. A wire with no signal stays
    at rest: off for a digital wire, ``park`` for an analog wire."""

    sample_rate: Frequency
    duration: Time
    signals: dict[WireName, Signal]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.sample_rate <= 0:
            raise ValueError("'sample_rate' must be greater than 0")
        if self.duration <= 0:
            raise ValueError("'duration' must be greater than 0")
        return self

    @property
    def samples(self) -> int:
        """The number of samples in 1 tick."""
        return round(self.sample_rate * self.duration)

    def windows(self) -> dict[WireName, Span]:
        """Each signal's start and end, in seconds. A signal whose edges cannot be placed is left out."""
        return _place_edges(self.signals, self.duration)[0]

    def violations(self, wires: Mapping[WireName, WireConfig]) -> Violations:
        """Return the problems of this timeline against the wires that its generator sends."""
        violations = Violations()
        known: dict[str, Signal] = {}
        for name, signal in self.signals.items():
            wire = wires.get(name)
            if wire is None:
                msg = f"'{name}' is not a wire that this generator sends."
                violations.add("timeline.signal.unexpected", msg, "signals", name)
                continue
            known[name] = signal
            if isinstance(wire, DigitalWire) != isinstance(signal, _DIGITAL_KINDS):
                takes = (
                    "on, off" if isinstance(wire, DigitalWire) else "constant, pulse, staircase, points, wave, follow"
                )
                msg = f"A {wire.kind} wire takes {takes}, not '{signal.kind}'."
                violations.add("timeline.signal.kind_mismatch", msg, "signals", name, "kind")
            else:
                violations += _unit_violations(signal, wire).under("signals", name)

        windows, problems = _place_edges(known, self.duration)
        for problem in problems:
            if problem.reason == "loop":
                msg = f"The edges form a loop: {problem.detail}."
            else:
                msg = (
                    f"'{problem.detail}' is not a signal in this timeline; an edge names a wire of the same generator."
                )
            violations.add(f"timeline.signal.edge_{problem.reason}", msg, "signals", problem.signal)
        for name, (start, end) in windows.items():
            if start < -_EDGE_TOLERANCE or end > self.duration + _EDGE_TOLERANCE:
                msg = (
                    f"The window {start * 1e3:g} to {end * 1e3:g} ms is outside the "
                    f"timeline of {self.duration * 1e3:g} ms."
                )
                violations.add("timeline.signal.window_outside_timeline", msg, "signals", name)
            elif end < start - _EDGE_TOLERANCE:
                msg = f"'end' ({end * 1e3:g} ms) is before 'start' ({start * 1e3:g} ms)."
                violations.add("timeline.signal.window_reversed", msg, "signals", name)
        return violations


def _unit_violations(signal: object, wire: WireConfig) -> Violations:
    violations = Violations()
    if isinstance(wire, AnalogWire):
        for path, value in _values(signal):
            if value.unit != wire.unit:
                msg = f"{value} is not in this wire's unit, {wire.unit}."
                violations.add("timeline.signal.unit_mismatch", msg, *path)
    return violations


def _values(signal: object) -> list[tuple[ViolationLoc, Quantity]]:
    """Each value of an analog signal that must be in its wire's unit, with its path in the signal."""
    found: list[tuple[ViolationLoc, Quantity]]
    match signal:
        case AnalogConstant(value=value):
            found = [(("value",), value)]
        case AnalogPulse(idle=idle, active=active):
            found = [(("idle",), idle), (("active",), active)]
        case AnalogStaircase(first=first, last=last):
            found = [(("first",), first), (("last",), last)]
        case AnalogPoints(points=points):
            found = [(("points", index, 1), value) for index, (_, value) in enumerate(points)]
        case AnalogWave(center=center, amplitude=amplitude):
            found = [(("center",), center), (("amplitude",), amplitude)]
        case _:
            found = []
    correction = getattr(signal, "correction", None)
    if isinstance(correction, Correction):
        found += [(("correction", index // 2, index % 2), value) for index, value in enumerate(correction.values)]
    return found


__all__ = [
    "AnalogConstant",
    "AnalogFollow",
    "AnalogPoints",
    "AnalogPulse",
    "AnalogStaircase",
    "AnalogWave",
    "Correction",
    "DigitalOff",
    "DigitalOn",
    "Edge",
    "EdgeName",
    "Signal",
    "SignalEdge",
    "Timeline",
    "TimelineEdge",
]
