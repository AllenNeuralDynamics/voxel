from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel

from vxl.daq.analog.ni import NiOnDemandAO
from vxl.daq.digital.ni import NiOnDemandDO
from vxl.daq.hub_ni import NiDaqmx

from .pulse import PulseDiscreteAxis


class SlotSpec(BaseModel):
    """One slot's wiring: the output pin that selects it, and its label."""

    pin: str
    label: str | None = None


class NiDiscreteAxis(PulseDiscreteAxis):
    """Discrete axis driven directly by an NI-DAQmx card, one output per slot.

    Builds a dedicated ``NiOnDemandAO`` or ``NiOnDemandDO`` on ``hub`` from the
    per-slot pins, then pulses it like any other on-demand generator. The initial
    home acquires the required lease, which remains held for the device lifetime so
    every move has deterministic access to its outputs. ``halt`` restores the
    inactive level without releasing the lease; ``close`` releases the task and
    lease.

    Each slot's pin and label are declared together via ``slots``. Homes to slot 0 at
    construction.
    """

    def __init__(
        self,
        uid: str,
        *,
        hub: NiDaqmx,
        slots: Mapping[int | str, SlotSpec],
        slot_count: int | None = None,
        output: Literal["ao", "do"] = "ao",
        active: bool | float | None = None,
        inactive: bool | float | None = None,
    ) -> None:
        """Initialize an NI-DAQmx-driven discrete axis.

        Args:
            uid: Unique identifier for this device.
            hub: NI-DAQmx hub owning the card the slot pins live on.
            slots: Slot index to ``{pin, label}``, e.g. ``{0: {pin: ao6, label: GFP}}``.
            slot_count: Total slots; inferred from ``slots`` when None.
            output: Output family to use. ``"ao"`` is analog; ``"do"`` is digital.
            active: Asserted output level. Defaults to 5 V for AO and ``True`` for DO.
            inactive: Resting output level. Defaults to 0 V for AO and ``False`` for DO.
        """
        specs = {int(k): SlotSpec.model_validate(v) for k, v in slots.items()}
        terminals = {str(i): spec.pin for i, spec in specs.items()}
        if output == "ao":
            generator = NiOnDemandAO(uid=f"{uid}_od", hub=hub, ports=terminals)
        elif output == "do":
            generator = NiOnDemandDO(uid=f"{uid}_od", hub=hub, lines=terminals)
        else:
            raise ValueError(f"output must be 'ao' or 'do', got {output!r}")

        try:
            super().__init__(
                uid=uid,
                generator=generator,
                slots={i: s.label for i, s in specs.items()},
                slot_count=slot_count,
                active=active,
                inactive=inactive,
            )
        except Exception:
            generator.reset()
            raise
