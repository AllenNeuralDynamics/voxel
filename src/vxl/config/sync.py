"""What each signal generator sends during 1 frame of a profile, and the checks of those signals against the nets."""

from typing import Self

from pydantic import Field, model_validator
from vxlib.schema import FrozenModel
from vxlib.units import Frequency, Quantity, Time

from vxl.signals.types import (
    ANALOG_TYPES,
    DIGITAL_TYPES,
    AnalogConstant,
    AnalogPoints,
    AnalogPulse,
    AnalogStaircase,
    AnalogWave,
    Correction,
    Signal,
    resolve_windows,
)

from .hal import HALConfig
from .identifiers import NetName
from .nets import DigitalNet, Net
from .violations import Violation, ViolationLoc, not_configured

_EDGE_TOLERANCE = 1e-12


class GeneratorSync(FrozenModel):
    """What 1 signal generator sends during 1 frame."""

    sample_rate: Frequency
    duration: Time
    signals: dict[NetName, Signal] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.sample_rate <= 0:
            raise ValueError("'sample_rate' must be greater than 0")
        if self.duration <= 0:
            raise ValueError("'duration' must be greater than 0")
        return self


def sync_violations(
    hal: HALConfig,
    generator: str,
    sync: GeneratorSync,
    *,
    loc: ViolationLoc,
) -> list[Violation]:
    if generator not in hal.device_uids:
        return [not_configured("Device", generator, code="imaging.profile.sync_device_missing", loc=loc)]
    violations = []
    nets = hal.nets.get(generator, {})
    signals_loc = (*loc, "signals")
    for name, signal in sync.signals.items():
        net = nets.get(name)
        if net is None:
            violations.append(
                Violation(
                    code="imaging.signal.net_missing",
                    msg=f"'{generator}' sends no net '{name}' (hal.nets.{generator}).",
                    loc=(*signals_loc, name),
                )
            )
            continue
        violations += _signal_kind_violations(signal, net, loc=(*signals_loc, name))

    windows, problems = resolve_windows(sync.signals, sync.duration)
    for problem in problems:
        if problem.reason == "loop":
            msg = f"The edges form a loop: {problem.detail}."
        else:
            msg = f"No signal '{problem.detail}' in this generator's signals."
        violations.append(
            Violation(code=f"imaging.signal.edge_{problem.reason}", msg=msg, loc=(*signals_loc, problem.signal))
        )
    for name, window in windows.items():
        if window.start < -_EDGE_TOLERANCE or window.end > sync.duration + _EDGE_TOLERANCE:
            violations.append(
                Violation(
                    code="imaging.signal.window_outside_frame",
                    msg=(
                        f"The window {window.start * 1e3:g} to {window.end * 1e3:g} ms is outside the frame "
                        f"of {sync.duration * 1e3:g} ms."
                    ),
                    loc=(*signals_loc, name),
                )
            )
        elif window.end < window.start - _EDGE_TOLERANCE:
            violations.append(
                Violation(
                    code="imaging.signal.window_reversed",
                    msg=f"'end' ({window.end * 1e3:g} ms) is before 'start' ({window.start * 1e3:g} ms).",
                    loc=(*signals_loc, name),
                )
            )
    return violations


def _signal_kind_violations(signal: object, net: Net, *, loc: ViolationLoc) -> list[Violation]:
    if isinstance(net, DigitalNet):
        if isinstance(signal, DIGITAL_TYPES):
            return []
        return [
            Violation(
                code="imaging.signal.kind_mismatch",
                msg="A digital net takes 'on', 'pulse' without levels, or 'train'.",
                loc=loc,
            )
        ]
    if not isinstance(signal, ANALOG_TYPES):
        return [
            Violation(
                code="imaging.signal.kind_mismatch",
                msg="An analog net takes 'constant', 'pulse' with levels, 'staircase', 'points', 'wave' or 'follow'.",
                loc=loc,
            )
        ]
    return [
        Violation(
            code="imaging.signal.unit_mismatch",
            msg=f"{value} is not in this net's unit, {net.analog.unit}.",
            loc=(*loc, *path),
        )
        for path, value in _values(signal)
        if value.unit != net.analog.unit
    ]


def _values(signal: object) -> list[tuple[ViolationLoc, Quantity]]:
    """Each value of an analog signal that must be in its net's unit, with its path in the signal."""
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


__all__ = ["GeneratorSync", "sync_violations"]
