"""Turns 1 generator's timeline into the samples each of its wires sends."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from scipy.interpolate import PchipInterpolator
from vxlib.problems import Problems
from vxlib.vector import Span

from vxl.core.instrument.config import AnalogWire, DigitalWire, WireConfig, WireName
from vxl.core.instrument.signals import (
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
)

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
        smooth, turn = _smooth(ideal, wire, rate)
        output, outside = _output(smooth, signal, wire)
        samples[name] = WireSamples(ideal, smooth, output)
        problems = _sample_problems(ideal, smooth, turn, output, outside, wire, window, timeline)
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


def _smooth(ideal: np.ndarray, wire: WireConfig, rate: float) -> tuple[np.ndarray, int]:
    """The shape the device can follow, and the time of each turn in samples. Each try blurs ``ideal``, then stretches
    it back to the sharp low and high. The narrowest blur that stays within the wire's acceleration wins; when none
    does, the one that reaches the most of the sharp swing."""
    if not isinstance(wire, AnalogWire) or wire.travel_time is None:
        return ideal, 0
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
    return attempt(best)[0], 2 * (best - 1) + max(jerk - 1, 0)


def _output(smooth: np.ndarray, signal: Signal, wire: WireConfig) -> tuple[dict[str, np.ndarray], list[str]]:
    """What goes out in each unit: ``smooth`` through the correction, which leaves a value outside its table as it
    is, then through each scale table down to V, which holds a value outside it at the table's end. Also the tables
    that some value fell outside: ``correction``, or the unit a scale starts from."""
    if isinstance(wire, DigitalWire):
        off = 0.0 if wire.off is None else float(wire.off)
        on = 1.0 if wire.on is None else float(wire.on)
        return {"V": off + (on - off) * smooth}, []
    outside: list[str] = []
    values = smooth
    if (correction := getattr(signal, "correction", None)) is not None:
        rows = correction.rows
        corrected = _table([float(w) for w, _ in rows], [float(s) for _, s in rows], values)
        if np.isnan(corrected).any():
            outside.append("correction")
        values = np.where(np.isnan(corrected), values, corrected)
    output = {wire.unit: values}
    for upper, lower in pairwise(wire.units):
        table = wire.scales[upper]
        scaled = _table(table[upper], table[lower], values)
        if np.isnan(scaled).any():
            outside.append(upper)
            scaled = _table(table[upper], table[lower], values, clip=True)
        values = output[lower] = scaled
    return output, outside


def _sample_problems(
    ideal: np.ndarray,
    smooth: np.ndarray,
    turn: int,
    output: Mapping[str, np.ndarray],
    outside: list[str],
    wire: WireConfig,
    window: Span,
    timeline: Timeline,
) -> Problems:
    """Every problem in 1 wire's samples."""
    rate, n = float(timeline.sample_rate), timeline.samples
    found = Problems()

    def add(code: str, msg: str, *at: str) -> None:
        found.add(f"timeline.signal.{code}", msg, *at)

    if isinstance(wire, DigitalWire):
        on = round(window.b * rate) - round(window.a * rate)
        if 0 < on < n and ideal.any():
            for key, value in {"on_time": on / rate, "off_time": (n - on) / rate, "repeat_time": n / rate}.items():
                if (least := getattr(wire, key)) is not None and value < least * (1 - _TOLERANCE):
                    name = key.replace("_", " ")
                    add(key, f"The {name} is {value * 1e3:g} ms; the receiver needs {least * 1e3:g} ms.")
        return found

    unit, swing, reached = wire.unit, float(np.ptp(ideal)), float(np.ptp(smooth))
    if reached < swing * (1 - 1e-6):
        add(
            "swing_short",
            f"The device cannot turn fast enough for the full swing; it reaches {reached:g} of {swing:g} {unit}.",
        )
    if turn > 0 and (closest := _closest_breaks(ideal, _acceleration_limit(wire, rate))) is not None:
        at, apart = closest
        if apart < turn:
            add(
                "turn_overlap",
                f"At {at / rate * 1e3:g} ms, 2 turns are {apart / rate * 1e3:g} ms apart, but each turn takes "
                f"{turn / rate * 1e3:g} ms.",
            )
    for table in outside:
        if table == "correction":
            add("outside_table", "Some values are outside the correction table; they are sent as is.", "correction")
        else:
            add("outside_table", f"Some values are outside the scale from {table}; they are held at its ends.")
    # Limits in the wire's own unit check the values wanted; limits in the units below check the output.
    found += _limit_problems({**output, unit: smooth}, wire)
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


__all__ = ["Rendered", "WireSamples", "render"]
