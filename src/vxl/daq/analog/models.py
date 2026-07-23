"""Pydantic models for analog-output signals.

Defines the declarative ``AOSignals`` config handed to ``AnalogOutputController.load()``,
plus the ``ClockSource`` discriminated union and the derived-waveform resolution
machinery (``AOSignals.arrays`` + ``DerivedResolutionError``).
"""

from collections.abc import Mapping
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Discriminator, Field
from vxlib.quantity import Frequency, Time

from .wave import BaseWaveform, DerivedMirror, DerivedOffset, DerivedScale, DerivedShift, Waveform


class InternalClock(BaseModel):
    """DAQ-generated clock. Frequency derives from ``duration + rest_time``.

    ``out_pin`` (optional) is a logical trigger name present in the device's
    init-time ``triggers`` map. When set, the driver routes the internal clock's
    rising edge to that physical PFI pin so downstream devices (e.g. cameras) can
    ride the frame clock. Leave it ``None`` when no external consumer needs the
    pulse — the AO task will still be retriggered by the card-internal terminal.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["internal"] = "internal"
    out_pin: str | None = None


class ExternalClock(BaseModel):
    """Trigger comes from an input pin on the AO device.

    ``source`` is a logical name that must exist in the device's init-time
    ``triggers`` map; the driver resolves it to a physical PFI at load-time.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["external"] = "external"
    source: str


ClockSource = Annotated[InternalClock | ExternalClock, Discriminator("type")]


# ==================== Derived waveform resolution ====================


class DerivedResolutionError(ValueError):
    """Raised when derived waveforms cannot be resolved (missing source / cycle)."""


_DerivedAny = DerivedMirror | DerivedScale | DerivedOffset | DerivedShift


def _topo_order(waveforms: Mapping[str, Waveform]) -> list[str]:
    """Return waveform keys in dependency order (sources before derived).

    Raises ``DerivedResolutionError`` on missing sources or cycles.
    """
    unresolved: list[str] = []
    for name, wf in waveforms.items():
        if isinstance(wf, _DerivedAny):
            if wf.source not in waveforms:
                raise DerivedResolutionError(f"Derived waveform '{name}' references unknown source '{wf.source}'")
            unresolved.append(name)

    order: list[str] = [name for name, wf in waveforms.items() if not isinstance(wf, _DerivedAny)]
    resolved: set[str] = set(order)

    while unresolved:
        made_progress = False
        still_unresolved: list[str] = []
        for name in unresolved:
            wf = waveforms[name]
            if not isinstance(wf, _DerivedAny):
                continue
            if wf.source in resolved:
                order.append(name)
                resolved.add(name)
                made_progress = True
            else:
                still_unresolved.append(name)
        if not made_progress:
            raise DerivedResolutionError(
                f"Cycle or unresolvable source among derived waveforms: {sorted(still_unresolved)}"
            )
        unresolved = still_unresolved

    return order


def _apply_derived(op: Waveform, source_array: np.ndarray, source_rest: float) -> np.ndarray:
    """Apply a derived operation to a resolved source sample array."""
    if isinstance(op, DerivedMirror):
        return 2.0 * source_rest - source_array
    if isinstance(op, DerivedScale):
        return source_rest + op.factor * (source_array - source_rest)
    if isinstance(op, DerivedOffset):
        return source_array + float(op.delta)
    if isinstance(op, DerivedShift):
        n = len(source_array)
        shift_samples = round(op.fraction * n) % n if n else 0
        return np.roll(source_array, shift_samples)
    raise DerivedResolutionError(f"Unknown derived waveform: {type(op).__name__}")


def resolve_to_arrays(waveforms: Mapping[str, Waveform], num_samples: int) -> dict[str, np.ndarray]:
    """Produce one sample array per waveform key, resolving derived entries.

    Derived waveforms inherit their source's ``rest_voltage``. Cycles or missing
    sources raise ``DerivedResolutionError``.
    """
    order = _topo_order(waveforms)
    arrays: dict[str, np.ndarray] = {}
    rest_voltages: dict[str, float] = {}

    for name in order:
        wf = waveforms[name]
        if isinstance(wf, BaseWaveform):
            arrays[name] = wf.get_array(num_samples)
            rest_voltages[name] = float(wf.rest_voltage)
        elif isinstance(wf, _DerivedAny):
            arrays[name] = _apply_derived(wf, arrays[wf.source], rest_voltages[wf.source])
            rest_voltages[name] = rest_voltages[wf.source]
        else:
            raise DerivedResolutionError(f"Unknown waveform type for '{name}': {type(wf).__name__}")

    return arrays


# ==================== AOSignals ====================


class AOSignals(BaseModel):
    """Declarative description of one AO device's output configuration.

    The profile manager hands an ``AOSignals`` to ``AnalogOutputController.load()``
    per profile activation, per waveform edit. The controller diffs against its
    cached copy and picks the cheapest hardware path (no-op / hot-swap / rebuild).
    """

    model_config = ConfigDict(frozen=True)

    sample_rate: Frequency = Field(..., gt=0)
    duration: Time = Field(..., gt=0)
    rest_time: Time = Field(default=Time(0.0), ge=0)
    clock_src: ClockSource = Field(default_factory=InternalClock)
    waveforms: dict[str, Waveform]

    @property
    def num_samples(self) -> int:
        """Total AO samples per cycle (duration * sample_rate, floor)."""
        return int(float(self.sample_rate) * float(self.duration))

    @property
    def frame_frequency(self) -> float:
        """Cycle frequency: 1 / (duration + rest_time). Zero when total span is zero."""
        total = float(self.duration) + float(self.rest_time)
        return 1.0 / total if total > 0 else 0.0

    def arrays(self) -> dict[str, np.ndarray]:
        """Resolve ``self.waveforms`` to sample arrays at this config's ``num_samples``.

        Raises ``DerivedResolutionError`` on cycles or missing sources among derived
        waveforms.
        """
        return resolve_to_arrays(self.waveforms, self.num_samples)
