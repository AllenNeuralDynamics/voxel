"""Back-compat re-export shim.

The canonical definitions live in ``vxl.analog_out.wave``. This module re-exports
them so existing ``vxl.daq`` consumers (legacy ``SyncTask`` code, configs loaded
during migration) keep working until Phase 6 retires ``src/vxl/daq/``.

The ``Waveform`` union re-exported here is *narrower* than the canonical one —
it excludes the ``Derived`` variants because legacy ``SyncTask`` assumes every
waveform has ``voltage`` and ``get_array``. New code should import
``Waveform`` from ``vxl.analog_out.wave`` to get the full union including
derived entries.
"""

from typing import Annotated

from pydantic import Discriminator, Tag, TypeAdapter

from vxl.analog_out.wave import (
    BaseWaveform,
    CSVWaveform,
    Derived,
    DerivedMirror,
    DerivedOffset,
    DerivedScale,
    DerivedShift,
    MultiPointWaveform,
    PeriodicWaveform,
    PulseWaveform,
    SineWave,
    SquareWave,
    TriangleWave,
    is_derived,
)

# Narrower union used by legacy SyncTask — excludes Derived.
Waveform = Annotated[
    Annotated[SquareWave, Tag("square")]
    | Annotated[SineWave, Tag("sine")]
    | Annotated[TriangleWave, Tag("triangle")]
    | Annotated[TriangleWave, Tag("sawtooth")]
    | Annotated[MultiPointWaveform, Tag("multi_point")]
    | Annotated[PulseWaveform, Tag("pulse")]
    | Annotated[CSVWaveform, Tag("csv")],
    Discriminator(lambda v: v.get("type") if isinstance(v, dict) else getattr(v, "type", None)),
]


def validate_waveform(data: dict) -> Waveform:
    """Legacy validator: rejects Derived entries. Use vxl.analog_out.wave for full support."""

    return TypeAdapter(Waveform).validate_python(data)


__all__ = [
    "BaseWaveform",
    "CSVWaveform",
    "Derived",
    "DerivedMirror",
    "DerivedOffset",
    "DerivedScale",
    "DerivedShift",
    "MultiPointWaveform",
    "PeriodicWaveform",
    "PulseWaveform",
    "SineWave",
    "SquareWave",
    "TriangleWave",
    "Waveform",
    "is_derived",
    "validate_waveform",
]
