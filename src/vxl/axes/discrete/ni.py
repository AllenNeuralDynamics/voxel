from collections.abc import Mapping

from pydantic import BaseModel
from vxlib.quantity import VoltageRange

from vxl.daq.analog.ni import NiOnDemandAO
from vxl.daq.hub_ni import NiDaqmx

from .pulse import PulseDiscreteAxis


class SlotSpec(BaseModel):
    """One slot's wiring: the output pin that selects it, and its label."""

    pin: str
    label: str | None = None


class NiDiscreteAxis(PulseDiscreteAxis):
    """Discrete axis driven directly by an NI-DAQmx card, one output pin per slot.

    Builds a dedicated ``NiOnDemandAO`` on ``hub`` from the per-slot pins, then
    pulses it like any other on-demand generator. The initial home acquires the
    required AO-bank lease, which remains held for the device lifetime so every move
    has deterministic access to its outputs. ``halt`` restores the inactive voltage
    without releasing the lease; ``close`` releases the task and lease.

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
        pulse_voltage: VoltageRange | None = None,
    ) -> None:
        """Initialize an NI-DAQmx-driven discrete axis.

        Args:
            uid: Unique identifier for this device.
            hub: NI-DAQmx hub owning the card the slot pins live on.
            slots: Slot index to ``{pin, label}``, e.g. ``{0: {pin: ao6, label: GFP}}``.
            slot_count: Total slots; inferred from ``slots`` when None.
            pulse_voltage: Select-pulse levels (``max`` peak, ``min`` rest). Defaults to 0-5 V.
        """
        specs = {int(k): SlotSpec.model_validate(v) for k, v in slots.items()}
        generator = NiOnDemandAO(uid=f"{uid}_od", hub=hub, ports={str(i): s.pin for i, s in specs.items()})
        try:
            super().__init__(
                uid=uid,
                generator=generator,
                slots={i: s.label for i, s in specs.items()},
                slot_count=slot_count,
                pulse_voltage=pulse_voltage,
            )
        except Exception:
            generator.reset()
            raise
