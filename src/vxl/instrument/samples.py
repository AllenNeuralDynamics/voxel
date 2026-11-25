"""Turns 1 generator's timeline into the samples each of its wires sends."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from scipy.interpolate import PchipInterpolator
from vxlib.issues import Problems
from vxlib.units import Quantity
from vxlib.vector import Span

from vxl.instrument.signals import (
    AnalogConstant,
    AnalogFollow,
    AnalogPoints,
    AnalogPulse,
    AnalogStaircase,
    AnalogWave,
    DigitalOff,
    DigitalOn,
    Signal,
    Timeline,
    TimelineEdge,
    TuningField,
)
from vxl.wiring import AnalogWire, DigitalWire, WireConfig, WireName

_TOLERANCE = 1e-9


@dataclass(frozen=True)
class WireSamples:
    """1 wire's samples at each step: the sharp shape its signal asks for, the smooth shape the device can follow, and
    the output in each unit, from the wire's unit after the correction down to V."""

    ideal: np.ndarray
    smooth: np.ndarray
    output: dict[str, np.ndarray]

    @property
    def volts(self) -> np.ndarray:
        """What the generator puts out on the wire's pin."""
        return self.output["V"]


@dataclass(frozen=True)
class Rendered:
    """Each wire's samples during 1 timeline, and the problems in them."""

    wires: dict[WireName, WireSamples]
    problems: Problems


def render(timeline: Timeline, wires: Mapping[WireName, WireConfig]) -> Rendered:
    """Each wire's samples during 1 timeline, and the problems in them. A signal that the timeline's own checks reject
    is left out."""
    rate, n = float(timeline.sample_rate), timeline.samples
    found = Problems()
    if abs(timeline.duration * rate - n) > 1e-6:
        msg = f"{timeline.duration * 1e3:g} ms at {rate:g} Hz is not a whole number of samples."
        found.add("timeline.samples_not_whole", msg, "duration")
    windows = timeline.windows()
    samples: dict[WireName, WireSamples] = {}
    for name, signal in timeline.signals.items():
        wire, window = wires.get(name), windows.get(name)
        if wire is None or window is None or isinstance(signal, AnalogFollow):
            continue
        if isinstance(wire, DigitalWire) != isinstance(signal, DigitalOn | DigitalOff):
            continue
        ideal = _ideal(signal, window, timeline)
        smooth, smooth_problems = _smooth(ideal, wire, rate)
        output, output_problems = _output(smooth, signal, wire)
        samples[name] = WireSamples(ideal, smooth, output)
        problems = _timing_problems(wire, window, timeline) if ideal.any() else Problems()
        problems += smooth_problems
        problems += output_problems
        found += problems.under("signals", name)

    # Each follow copies the volts of its source, so it comes after it. A loop is never ready; the timeline's edge
    # checks report it.
    follows = {name: signal for name, signal in timeline.signals.items() if isinstance(signal, AnalogFollow)}
    while ready := [name for name, follow in follows.items() if follow.source in samples]:
        for name in ready:
            follow = follows.pop(name)
            source = samples[follow.source].volts
            copied = follow.scale * np.roll(source, round(follow.delay * rate)) + follow.offset
            samples[name] = WireSamples(copied, copied, {"V": copied})
            if isinstance(wire := wires.get(name), AnalogWire):
                found += _limit_problems({"V": copied}, wire).under("signals", name)
    return Rendered(samples, found)


def _ideal(signal: Signal, window: Span, timeline: Timeline) -> np.ndarray:
    """The sharp shape that ``signal`` asks for over the whole timeline, as if the device turned at once. In the gap a
    pulse rests at ``idle`` and every other shape goes straight back to its start."""
    rate, n = float(timeline.sample_rate), timeline.samples
    start, end = round(window.a * rate), round(window.b * rate)
    length = max(end - start, 1)
    x = np.arange(length) / length
    rest: float | None = None
    match signal:
        case DigitalOn():
            values = np.zeros(n)
            values[np.arange(start, end) % n] = 1.0
            return values
        case AnalogConstant(value=value):
            return np.full(n, float(value))
        case AnalogPulse(idle=idle, active=active):
            shape, rest = np.full(length, float(active)), float(idle)
        case AnalogStaircase(first=first, last=last, steps=steps):
            step = np.minimum(np.floor(x * steps), steps - 1)
            shape = first + (last - first) * step / (steps - 1)
        case AnalogPoints(points=points):
            shape = np.interp(x, [float(time) for time, _ in points], [float(level) for _, level in points])
        case AnalogWave(shape=kind, center=center, amplitude=amplitude, cycles=cycles, phase=phase, split=split):
            low, swing = center - amplitude, 2 * amplitude
            turns = cycles * x + phase / (2 * math.pi)
            p = turns - np.floor(turns)
            if kind == "square":
                shape = np.where(p < split, low + swing, low)
            elif split in (0, 1):
                ramp = p if split == 1 else 1 - p
                shape = low + swing * (ramp if kind == "triangle" else (1 - np.cos(np.pi * ramp)) / 2)
            elif kind == "triangle":
                shape = low + swing * np.where(p < split, p / split, 1 - (p - split) / (1 - split))
            else:
                rising = (1 - np.cos(np.pi * p / split)) / 2
                falling = (1 + np.cos(np.pi * (p - split) / (1 - split))) / 2
                shape = low + swing * np.where(p < split, rising, falling)
        case _:
            return np.zeros(n)
    if end <= start:
        return np.full(n, shape[0] if rest is None else rest)
    gap = n - length
    between = np.full(gap, rest) if rest is not None else np.linspace(shape[-1], shape[0], gap + 2)[1:-1]
    return np.roll(np.concatenate([shape, between]), start)


def _smooth(ideal: np.ndarray, wire: WireConfig, rate: float) -> tuple[np.ndarray, Problems]:
    """The shape the device can follow, and its problems: a swing it cannot reach, and 2 turns closer than the time
    of 1 turn. Each try blurs ``ideal``, then stretches it back to the sharp low and high. The narrowest blur that
    stays within the wire's acceleration wins; when none does, the one that reaches the most of the sharp swing."""
    found = Problems()
    if not isinstance(wire, AnalogWire) or wire.travel_time is None:
        return ideal, found
    limit = _acceleration_limit(wire, rate)
    jerk = round(float(wire.jerk_time or 0.0) * rate)
    swing = float(np.ptp(ideal))

    def attempt(width: int) -> tuple[np.ndarray, float]:
        blurred = _blur(ideal, width, jerk)
        reached = float(np.ptp(blurred))
        stretch = swing / reached if reached > 0 else 1.0
        acceleration = _acceleration(blurred)
        if acceleration > 0:
            stretch = min(stretch, limit / acceleration)
        if stretch < 1 - _TOLERANCE:
            return blurred, -math.inf
        middle = (float(ideal.max()) + float(ideal.min())) / 2
        values = middle + (blurred - (float(blurred.max()) + float(blurred.min())) / 2) * stretch
        return values, reached * stretch / swing if swing > 0 else 1.0

    widths = sorted({int(w) for w in np.geomspace(1, len(ideal), 64)})
    best, best_reach, below = 1, -math.inf, 0
    for width in widths:
        _, reach = attempt(width)
        if reach >= 1 - 1e-6:
            # The narrowest width that fits lies between the last miss and this one.
            low, high = below, width
            while high - low > 1:
                mid = (low + high) // 2
                low, high = (low, mid) if attempt(mid)[1] >= 1 - 1e-6 else (mid, high)
            best = high
            break
        if reach > best_reach:
            best, best_reach = width, reach
        below = width
    smooth, turn = attempt(best)[0], 2 * (best - 1) + max(jerk - 1, 0)
    if (reached := float(np.ptp(smooth))) < swing * (1 - 1e-6):
        msg = f"The device cannot turn fast enough for the full swing; it reaches {reached:g} of {swing:g} {wire.unit}."
        found.add("timeline.signal.swing_short", msg)
    if turn > 0 and (closest := _closest_breaks(ideal, limit)) is not None:
        at, apart = closest
        if apart < turn:
            msg = (
                f"At {at / rate * 1e3:g} ms, 2 turns are {apart / rate * 1e3:g} ms apart, but each turn takes "
                f"{turn / rate * 1e3:g} ms."
            )
            found.add("timeline.signal.turn_overlap", msg)
    return smooth, found


def _output(smooth: np.ndarray, signal: Signal, wire: WireConfig) -> tuple[dict[str, np.ndarray], Problems]:
    """What goes out in each unit, and its problems: ``smooth`` through the correction, which leaves a value outside
    its table as it is, then through each scale table down to V, which holds a value outside it at the table's end.
    The problems are each table that some value fell outside, and each limit that the values pass."""
    found = Problems()
    if isinstance(wire, DigitalWire):
        off = 0.0 if wire.off is None else float(wire.off)
        on = 1.0 if wire.on is None else float(wire.on)
        return {"V": off + (on - off) * smooth}, found
    values = smooth
    if (correction := getattr(signal, "correction", None)) is not None:
        rows = correction.rows
        corrected = _table([float(w) for w, _ in rows], [float(s) for _, s in rows], values)
        if np.isnan(corrected).any():
            msg = "Some values are outside the correction table; they are sent as is."
            found.add("timeline.signal.outside_table", msg, "correction")
        values = np.where(np.isnan(corrected), values, corrected)
    output = {wire.unit: values}
    for upper, lower in pairwise(wire.units):
        table = wire.scales[upper]
        scaled = _table(table[upper], table[lower], values)
        if np.isnan(scaled).any():
            msg = f"Some values are outside the scale from {upper}; they are held at its ends."
            found.add("timeline.signal.outside_table", msg)
            scaled = _table(table[upper], table[lower], values, clip=True)
        values = output[lower] = scaled
    # Limits in the wire's own unit check the values wanted; limits in the units below check the output.
    found += _limit_problems({**output, wire.unit: smooth}, wire)
    return output, found


def _timing_problems(wire: WireConfig, window: Span, timeline: Timeline) -> Problems:
    """The times of a digital wire that are shorter than its receiver needs: on, off, and from 1 start to the next."""
    found = Problems()
    if not isinstance(wire, DigitalWire):
        return found
    rate, n = float(timeline.sample_rate), timeline.samples
    on = round(window.b * rate) - round(window.a * rate)
    if not 0 < on < n:
        return found
    for key, value in {"on_time": on / rate, "off_time": (n - on) / rate, "repeat_time": n / rate}.items():
        if (least := getattr(wire, key)) is not None and value < least * (1 - _TOLERANCE):
            msg = f"The {key.replace('_', ' ')} is {value * 1e3:g} ms; the receiver needs {least * 1e3:g} ms."
            found.add(f"timeline.signal.{key}", msg)
    return found


def _limit_problems(values: Mapping[str, np.ndarray], wire: AnalogWire) -> Problems:
    """The limits in each unit, against the values in that unit."""
    found = Problems()
    for unit, limits in wire.limits.items():
        if (checked := values.get(unit)) is None:
            continue
        low, high = float(checked.min()), float(checked.max())
        margin = _TOLERANCE * max(abs(limits.low), abs(limits.high), 1.0)
        if low < limits.low - margin or high > limits.high + margin:
            msg = (
                f"The values reach {low:g} to {high:g} {unit}, outside the limits {limits.low:g} to "
                f"{limits.high:g} {unit}."
            )
            found.add("timeline.signal.limit", msg)
    return found


def _acceleration_limit(wire: AnalogWire, rate: float) -> float:
    """The largest change of speed the device takes in 1 sample, in the wire's unit per sample squared. Full speed
    on the way across the limits in ``travel_time`` means speeding up for half of it and slowing down for the rest."""
    span = wire.limits[wire.unit]
    return 4 * (span.high - span.low) / float(wire.travel_time or math.inf) ** 2 / rate**2


def _acceleration(values: np.ndarray) -> float:
    """The largest change of speed between 2 samples, with the timeline repeating."""
    return float(np.abs(np.roll(values, -1) - 2 * values + np.roll(values, 1)).max())


def _closest_breaks(ideal: np.ndarray, limit: float) -> tuple[int, int] | None:
    """Where the 2 closest breaks in ``ideal`` are, and how many samples apart. A break is a turn sharper than the
    device takes; a jump makes 2 sharp samples side by side, so neighbors count as 1 break."""
    sharp = np.abs(np.roll(ideal, -1) - 2 * ideal + np.roll(ideal, 1)) > limit * (1 + _TOLERANCE)
    found = np.flatnonzero(sharp & ~np.roll(sharp, 1))
    if len(found) == 0:
        return None
    apart = np.diff(found, append=found[0] + len(ideal))
    first = int(np.argmin(apart))
    return int(found[first]), int(apart[first])


def _blur(values: np.ndarray, width: int, jerk: int) -> np.ndarray:
    """``values`` averaged twice over ``width`` samples, then once over ``jerk`` samples, with the timeline repeating.
    2 averages make an S-shaped turn; the third softens how fast the turn starts."""
    for box in (width, width, jerk):
        if box > 1:
            wrapped = np.take(values, np.arange(-(box // 2), len(values) - box // 2 + box - 1), mode="wrap")
            sums = np.concatenate([[0.0], np.cumsum(wrapped)])
            values = (sums[box : box + len(values)] - sums[: len(values)]) / box
    return values


def _table(
    column_in: Sequence[float], column_out: Sequence[float], values: np.ndarray, *, clip: bool = False
) -> np.ndarray:
    """``values`` through a table, with a smooth curve that does not overshoot between rows. A value outside the table
    is NaN, or the nearest end with ``clip``."""
    x, y = np.asarray(column_in, dtype=float), np.asarray(column_out, dtype=float)
    if x[0] > x[-1]:
        x, y = x[::-1], y[::-1]
    return PchipInterpolator(x, y, extrapolate=False)(np.clip(values, x[0], x[-1]) if clip else values)


_LEVELS = frozenset({"value", "idle", "active", "first", "last", "center", "amplitude"})


def tune(
    timeline: Timeline,
    wires: Mapping[WireName, WireConfig],
    *,
    wire: WireName,
    field: TuningField,
    value: float,
    volts: Span,
) -> tuple[Timeline, float]:
    """``timeline`` with 1 number of the signal on ``wire`` set to ``value``, and the value applied. ``value`` is in
    the field's fixed unit: times in ms, levels in the wire's unit, ``phase`` in degrees, a follow's ``offset`` in V,
    and ``cycles``, ``split`` and ``scale`` in none. It is kept on the number's step and inside its bounds, and written
    in the unit the file used.

    An edge stays inside the timeline, a follow's ``delay`` within 1 duration either way, and a follow's ``offset`` and
    ``scale`` keep its volts inside the wire's limits. A level stays inside the wire's limits, or inside ``volts``,
    what the generator can put out, carried up through the wire's scales; an ``amplitude`` goes from 0 to half that
    range. The step is 1 sample for times, and a round number near 1/1000 of the bounds for the rest. Raise
    ``ValueError`` when the signal has no such field, or when the bounds depend on an edge or a signal that cannot be
    placed or rendered."""
    bounds, step = _tuning_bounds(timeline, wires, wire, field, volts)
    low, high = bounds.low, bounds.high
    if step is not None:
        value = round(value / step) * step
        low, high = math.ceil(low / step - 1e-9) * step, math.floor(high / step + 1e-9) * step
    applied = _tidy(min(max(value, low), high))
    signal, config = timeline.signals[wire], wires[wire]
    old = getattr(signal, field)
    match field:
        case "start" | "end":
            new = old.model_copy(update={"offset": _written(old.offset, applied * 1e-3)})
        case "delay":
            new = _written(old, applied * 1e-3)
        case "phase":
            new = _written(old, math.radians(applied))
        case "offset":
            new = _written(old, applied)
        case "cycles" | "split" | "scale":
            new = applied
        case _:
            new = Quantity.of(applied, config.unit if isinstance(config, AnalogWire) else old.unit)
    signals = {**timeline.signals, wire: signal.model_copy(update={field: new})}
    return timeline.model_copy(update={"signals": signals}), applied


@dataclass(frozen=True)
class Tuning:
    """1 number of a signal as a tuning knob turns it: its value now and its unit, and the bounds and step that
    :func:`tune` keeps it to. ``step`` is ``None`` for bounds with no end."""

    value: float
    unit: str
    bounds: Span
    step: float | None


def tuning(
    timeline: Timeline, wires: Mapping[WireName, WireConfig], *, wire: WireName, field: TuningField, volts: Span
) -> Tuning:
    """The number ``field`` of the signal on ``wire``, in the unit :func:`tune` takes it in. Raise ``ValueError`` as
    :func:`tune` does."""
    bounds, step = _tuning_bounds(timeline, wires, wire, field, volts)
    signal, config = timeline.signals[wire], wires[wire]
    old = getattr(signal, field)
    match field:
        case "start" | "end":
            value, unit = float(old.offset) * 1e3, "ms"
        case "delay":
            value, unit = float(old) * 1e3, "ms"
        case "phase":
            value, unit = math.degrees(float(old)), "°"
        case "offset":
            value, unit = float(old), "V"
        case "cycles" | "split" | "scale":
            value, unit = float(old), ""
        case _:
            value, unit = float(old.number), config.unit if isinstance(config, AnalogWire) else old.unit
    return Tuning(value=_tidy(value), unit=unit, bounds=bounds, step=step)


def _tuning_bounds(
    timeline: Timeline, wires: Mapping[WireName, WireConfig], wire: WireName, field: TuningField, volts: Span
) -> tuple[Span, float | None]:
    """The bounds and the step of 1 number, in the field's fixed unit, as :func:`tune` says. The step is ``None`` for
    bounds with no end."""
    signal, config = timeline.signals.get(wire), wires.get(wire)
    if signal is None or config is None:
        raise ValueError(f"'{wire}' has no signal on a wire of this generator")
    if field not in type(signal).model_fields:
        raise ValueError(f"A '{signal.kind}' signal has no '{field}'")
    sample_ms, duration_ms = 1e3 / timeline.sample_rate, timeline.duration * 1e3
    if field in ("start", "end"):
        edge = getattr(signal, field)
        if isinstance(edge, TimelineEdge):
            base = 0.0 if edge.timeline == "start" else float(timeline.duration)
        elif (window := timeline.windows().get(edge.signal)) is not None:
            base = window.a if edge.edge == "start" else window.b
        else:
            raise ValueError(f"The edge '{edge.signal}.{edge.edge}' cannot be placed")
        return Span(0 - base * 1e3, duration_ms - base * 1e3), sample_ms
    if field == "delay":
        return Span(-duration_ms, duration_ms), sample_ms
    if field == "phase":
        return Span(0.0, 360.0), _round_step(360.0)
    if field == "split":
        return Span(0.0, 1.0), _round_step(1.0)
    if field == "cycles":
        window = timeline.windows().get(wire)
        most = 0.0 if window is None else round(window.length * timeline.sample_rate) / 2
        if (step := _round_step(most)) is None:
            raise ValueError(f"The window of '{wire}' cannot be placed or has no samples")
        return Span(step, most), step  # above 0: the smallest number on the step
    if not isinstance(config, AnalogWire):
        raise ValueError(f"'{wire}' is not an analog wire")
    if field in _LEVELS:
        span = _level_span(config, volts)
        if field == "amplitude":  # half the swing, not a level; a negative one only flips the wave, as phase does
            span = Span(0.0, span.length / 2)
        return span, _round_step(span.length)
    return _follow_bounds(timeline, wires, wire, field, config.limits.get("V", volts))


def _level_span(wire: AnalogWire, volts: Span) -> Span:
    """The values ``wire`` can take in its unit: its limits in the highest unit that has them, or ``volts``, carried up
    through the scale tables read backward."""
    units = wire.units
    top = next((index for index, unit in enumerate(units) if unit in wire.limits), len(units) - 1)
    span = wire.limits.get(units[top], volts)
    for upper, lower in reversed(list(pairwise(units[: top + 1]))):
        table = wire.scales[upper]
        carried = _table(table[lower], table[upper], np.array([span.a, span.b]), clip=True)
        span = Span(float(carried.min()), float(carried.max()))
    return Span(span.low, span.high)


def _follow_bounds(
    timeline: Timeline, wires: Mapping[WireName, WireConfig], wire: WireName, field: TuningField, limits: Span
) -> tuple[Span, float | None]:
    """The ``offset`` or ``scale`` of a follow that keeps its copied volts inside ``limits``, and its step."""
    follow = timeline.signals[wire]
    if not isinstance(follow, AnalogFollow) or (source := render(timeline, wires).wires.get(follow.source)) is None:
        raise ValueError(f"The source of '{wire}' cannot be rendered")
    ends = (float(source.volts.min()), float(source.volts.max()))
    if field == "offset":
        copied = [follow.scale * end for end in ends]
        low, high = limits.low - min(copied), limits.high - max(copied)
    else:
        low, high = -math.inf, math.inf
        for end in ends:
            if end != 0:
                a, b = (limits.low - follow.offset) / end, (limits.high - follow.offset) / end
                low, high = max(low, min(a, b)), min(high, max(a, b))
    if low > high:
        raise ValueError(f"No {field} keeps the volts of '{wire}' inside {limits.low:g} to {limits.high:g} V")
    span = Span(low, high)
    return span, _round_step(span.length)


def _written(old: Quantity, base: float) -> Quantity:
    """A value of the kind of ``old``, in its unit, from a number in the kind's base unit."""
    factor = 1.0 if old.UNITS is None else old.UNITS[old.unit]
    return type(old).of(_tidy(base / factor), old.unit)


def _tidy(number: float) -> float:
    """``number`` at 12 significant digits, so a sum of steps such as ``0.1 * 3`` is saved as ``0.3``."""
    return float(f"{number:.12g}")


def _round_step(length: float) -> float | None:
    """A power of 10 near 1/1000 of ``length``, or ``None`` for a length that is 0 or has no end."""
    if not math.isfinite(length) or length <= 0:
        return None
    return 10.0 ** math.floor(math.log10(length / 1000))


__all__ = ["Rendered", "Tuning", "WireSamples", "render", "tune", "tuning"]
