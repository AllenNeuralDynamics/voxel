"""``hal.wiring``: every wire, by the device that sends it, and the timelines that signal generators play on them."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Annotated, Any, Literal, NamedTuple, Self

from pydantic import AfterValidator, BeforeValidator, ConfigDict, Field, PlainSerializer, RootModel, model_validator
from rigup.config import DeviceUid
from vxlib.schema import FrozenModel, check_identifier, identifier, repeated
from vxlib.units import Angle, Frequency, Percent, Quantity, Time, Voltage
from vxlib.vector import Span

from vxl.config.basics import Violation, ViolationLoc, WireName, not_configured, under

Connector = Annotated[str, identifier("Connector")]
"""A connector, named as it is on the hardware."""


class Pin(NamedTuple):
    """A connector of a device or a part, written ``camera/trigger_in``."""

    device: str
    connector: str

    def __str__(self) -> str:
        return f"{self.device}/{self.connector}"


def _read_pin(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    device, sep, connector = value.partition("/")
    if not sep or "/" in connector:
        raise ValueError(f"a pin is written 'device/connector', got {value!r}")
    return Pin(check_identifier(device, "Device UID"), check_identifier(connector, "Connector"))


def _unique(value: list[Pin]) -> list[Pin]:
    if duplicates := repeated(value):
        raise ValueError(f"pins in 'to' must be unique (repeated: {[str(pin) for pin in duplicates]})")
    return value


Pins = Annotated[
    list[Annotated[Pin, BeforeValidator(_read_pin), PlainSerializer(str, return_type=str)]],
    AfterValidator(_unique),
]
"""The pins a wire reaches, each once."""


_UnitName = Annotated[str, Field(min_length=1)]
"""The name of a unit, such as ``V``, ``mm`` or ``deg``."""


class DigitalWire(FrozenModel):
    """A wire that is on or off. ``off`` and ``on`` are given only when the sending pin is analog; the times are the
    shortest pulse, gap and period the receiver accepts."""

    pin: Connector
    to: Pins
    kind: Literal["digital"]
    off: Voltage | None = None
    on: Voltage | None = None
    on_time: Time | None = None
    off_time: Time | None = None
    repeat_time: Time | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.off is None) != (self.on is None):
            raise ValueError("give both 'off' and 'on', or neither")
        if self.off is not None and self.off == self.on:
            raise ValueError("'off' and 'on' must differ")
        for name in ("on_time", "off_time", "repeat_time"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"'{name}' must be greater than 0")
        return self


class AnalogWire(FrozenModel):
    """A wire that carries a value in its own ``unit``. ``scales`` lead from that unit down to volts, 1 table
    per step, such as ``{mm: {mm: [...], deg: [...]}, deg: {deg: [...], V: [...]}}``. ``limits`` may use any unit on
    that path."""

    pin: Connector
    to: Pins
    kind: Literal["analog"]
    unit: _UnitName = "V"
    scales: dict[_UnitName, dict[_UnitName, list[float]]] = Field(default_factory=dict)
    limits: dict[_UnitName, Span] = Field(default_factory=dict)
    park: Quantity | None = None
    travel_time: Time | None = None
    jerk_time: Time | None = None

    @property
    def units(self) -> list[_UnitName]:
        """The units a value passes through, from the wire's unit down to V."""
        path = [self.unit]
        while path[-1] != "V" and path[-1] in self.scales:
            below = next(key for key in self.scales[path[-1]] if key != path[-1])
            if below in path:
                break
            path.append(below)
        return path

    @model_validator(mode="after")
    def _check(self) -> Self:
        for unit, table in self.scales.items():
            _check_scale(unit, table)
        path = self.units
        if path[-1] != "V":
            raise ValueError(f"scales must lead from '{self.unit}' down to 'V' (they stop at '{path[-1]}')")
        if unused := sorted(set(self.scales) - set(path)):
            raise ValueError(f"scales for {unused} are not on the path from '{self.unit}' to 'V'")
        for unit, limits in self.limits.items():
            if unit not in path:
                raise ValueError(f"limits in '{unit}' are not on the path {path}")
            if limits.length == 0:
                raise ValueError(f"limits in '{unit}' need 2 different numbers, got {list(limits)}")
        if self.park is not None:
            self._check_park(self.park)
        if self.travel_time is not None and self.travel_time <= 0:
            raise ValueError("'travel_time' must be greater than 0")
        if self.travel_time is not None and self.unit not in self.limits:
            raise ValueError(f"'travel_time' is the time to cross the limits, so it needs limits in '{self.unit}'")
        if self.jerk_time is not None:
            if self.travel_time is None:
                raise ValueError("'jerk_time' needs 'travel_time'")
            if self.jerk_time <= 0:
                raise ValueError("'jerk_time' must be greater than 0")
        return self

    def _check_park(self, park: Quantity) -> None:
        if park.unit != self.unit:
            raise ValueError(f"park is in {park.unit}; this wire's unit is {self.unit}")
        if self.unit in self.limits:
            limits = self.limits[self.unit]
            if not limits.low <= park <= limits.high:
                raise ValueError(f"park {park} is outside the limits [{limits.low}, {limits.high}] {self.unit}")


def _check_scale(unit: str, table: Mapping[str, list[float]]) -> None:
    if unit == "V":
        raise ValueError("'V' needs no scale")
    if unit not in table or len(table) != 2:
        raise ValueError(f"the scale for '{unit}' needs 2 columns: '{unit}' and the unit below it")
    columns = list(table.values())
    if len(columns[0]) != len(columns[1]) or len(columns[0]) < 2:
        raise ValueError(f"the columns of the scale for '{unit}' need the same length, at least 2")
    for name, column in table.items():
        steps = [b - a for a, b in pairwise(column)]
        if not (all(step > 0 for step in steps) or all(step < 0 for step in steps)):
            raise ValueError(f"column '{name}' of the scale for '{unit}' must rise or fall at every row")


type WireConfig = Annotated[DigitalWire | AnalogWire, Field(discriminator="kind")]


@dataclass(frozen=True)
class Wire:
    """1 wire, as ``Wiring.between`` reports it."""

    sender: str
    name: str
    config: DigitalWire | AnalogWire

    def inputs_on(self, device: str) -> list[str]:
        """The connectors of ``device`` that this wire reaches, such as ``PFI0``."""
        return [pin.connector for pin in self.config.to if pin.device == device]


class Wiring(RootModel[dict[DeviceUid, dict[WireName, WireConfig]]]):
    """``hal.wiring``: each sending device's wires, by name."""

    model_config = ConfigDict(frozen=True)

    def outputs(self, device: str) -> dict[WireName, DigitalWire | AnalogWire]:
        """Every wire that ``device`` sends, by name."""
        return dict(self.root.get(device, {}))

    def between(self, sender: str, receiver: str) -> list[Wire]:
        """Every wire from ``sender`` that reaches ``receiver``."""
        return [
            Wire(sender, name, config)
            for name, config in self.outputs(sender).items()
            if any(pin.device == receiver for pin in config.to)
        ]

    def violations(self, *, devices: Collection[str], parts: Collection[str]) -> list[Violation]:
        """Return the problems of the wiring that ``hal`` alone shows."""
        violations: list[Violation] = []
        owner: dict[str, tuple[str, str]] = {}

        def claim(pin: str, sender: str, name: str, pin_loc: ViolationLoc) -> None:
            if pin in owner:
                first_sender, first_name = owner[pin]
                violations.append(
                    Violation(
                        code="hal.wiring.pin_shared",
                        msg=f"Pin '{pin}' is already in wire '{first_sender}.{first_name}'.",
                        loc=pin_loc,
                    )
                )
            else:
                owner[pin] = (sender, name)

        for sender, group in self.root.items():
            if sender not in devices:
                violations.append(not_configured("Device", sender, code="hal.wiring.device_missing", loc=(sender,)))
                continue
            for name, wire in group.items():
                wire_loc = (sender, name)
                claim(f"{sender}/{wire.pin}", sender, name, (*wire_loc, "pin"))
                for index, pin in enumerate(wire.to):
                    if pin.device not in devices and pin.device not in parts:
                        violations.append(
                            Violation(
                                code="hal.wiring.receiver_missing",
                                msg=f"'{pin.device}' is not a device or a part; declare a part in hal.parts.",
                                loc=(*wire_loc, "to", index),
                            )
                        )
                    else:
                        claim(str(pin), sender, name, (*wire_loc, "to", index))
        return violations


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
    """What 1 signal generator plays on each tick, with 1 signal for each wire it plays."""

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

    def violations(self, wires: Mapping[WireName, WireConfig]) -> list[Violation]:
        """Return the problems of this timeline against the wires its generator plays."""
        violations = [
            Violation(code="imaging.signal.missing", msg=f"Wire '{name}' needs a signal.", loc=("signals",))
            for name in wires
            if name not in self.signals
        ]
        known: dict[str, Signal] = {}
        for name, signal in self.signals.items():
            wire = wires.get(name)
            signal_loc = ("signals", name)
            if wire is None:
                violations.append(
                    Violation(
                        code="imaging.signal.unexpected",
                        msg=f"'{name}' is not a wire that this generator plays.",
                        loc=signal_loc,
                    )
                )
                continue
            known[name] = signal
            if isinstance(wire, DigitalWire) != isinstance(signal, _DIGITAL_KINDS):
                takes = (
                    "on, off" if isinstance(wire, DigitalWire) else "constant, pulse, staircase, points, wave, follow"
                )
                violations.append(
                    Violation(
                        code="imaging.signal.kind_mismatch",
                        msg=f"A {wire.kind} wire takes {takes}, not '{signal.kind}'.",
                        loc=(*signal_loc, "kind"),
                    )
                )
            else:
                violations += under(signal_loc, _unit_violations(signal, wire))

        windows, problems = _place_edges(known, self.duration)
        for problem in problems:
            if problem.reason == "loop":
                msg = f"The edges form a loop: {problem.detail}."
            else:
                msg = (
                    f"'{problem.detail}' is not a signal in this timeline; an edge names a wire of the same generator."
                )
            violations.append(
                Violation(code=f"imaging.signal.edge_{problem.reason}", msg=msg, loc=("signals", problem.signal))
            )
        for name, (start, end) in windows.items():
            if start < -_EDGE_TOLERANCE or end > self.duration + _EDGE_TOLERANCE:
                violations.append(
                    Violation(
                        code="imaging.signal.window_outside_timeline",
                        msg=(
                            f"The window {start * 1e3:g} to {end * 1e3:g} ms is outside the "
                            f"timeline of {self.duration * 1e3:g} ms."
                        ),
                        loc=("signals", name),
                    )
                )
            elif end < start - _EDGE_TOLERANCE:
                violations.append(
                    Violation(
                        code="imaging.signal.window_reversed",
                        msg=f"'end' ({end * 1e3:g} ms) is before 'start' ({start * 1e3:g} ms).",
                        loc=("signals", name),
                    )
                )
        return violations


def _unit_violations(signal: object, wire: WireConfig) -> list[Violation]:
    if not isinstance(wire, AnalogWire):
        return []
    return [
        Violation(
            code="imaging.signal.unit_mismatch",
            msg=f"{value} is not in this wire's unit, {wire.unit}.",
            loc=path,
        )
        for path, value in _values(signal)
        if value.unit != wire.unit
    ]


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
    "AnalogWire",
    "Connector",
    "Correction",
    "DigitalOff",
    "DigitalOn",
    "DigitalWire",
    "Edge",
    "EdgeName",
    "Pin",
    "Pins",
    "Signal",
    "SignalEdge",
    "Timeline",
    "TimelineEdge",
    "Wire",
    "WireConfig",
    "Wiring",
]
