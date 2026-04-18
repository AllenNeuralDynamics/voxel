"""Pydantic models for analog-output signals.

Defines the declarative ``AOSignals`` config handed to ``AnalogOutputController.load()``,
plus the ``ClockSource`` discriminated union.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field
from vxlib.quantity import Frequency, Time

from .wave import Waveform


class InternalClock(BaseModel):
    """DAQ-generated clock. Frequency derives from ``duration + rest_time``."""

    model_config = ConfigDict(frozen=True)

    type: Literal["internal"] = "internal"


class ExternalClock(BaseModel):
    """Trigger comes from an input pin on the AO device.

    ``source`` is a logical name that must exist in the device's init-time
    ``triggers`` map; the driver resolves it to a physical PFI at load-time.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["external"] = "external"
    source: str


ClockSource = Annotated[InternalClock | ExternalClock, Discriminator("type")]


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
