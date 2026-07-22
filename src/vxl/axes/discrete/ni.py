from collections.abc import Mapping

from pydantic import BaseModel

from vxl.analog_out.ni import NiAnalogOutput, NiDaqmx

from .analog_out import AnalogOutDiscreteAxis


class SlotSpec(BaseModel):
    """One slot's wiring: the analog-output pin that selects it, and its label."""

    pin: str
    label: str | None = None


class NiDiscreteAxis(AnalogOutDiscreteAxis):
    """Discrete axis driven directly by an NI-DAQmx card, one AO pin per slot.

    Builds a dedicated ``NiAnalogOutput`` on ``hub`` from the per-slot pins, then
    drives it like any other function generator. Each slot's pin and label are
    declared together via ``slots``. Homes to slot 0 at construction.
    """

    def __init__(
        self,
        uid: str,
        *,
        hub: NiDaqmx,
        slots: Mapping[int | str, SlotSpec],
        slot_count: int | None = None,
    ) -> None:
        """Initialize an NI-DAQmx-driven discrete axis.

        Args:
            uid: Unique identifier for this device.
            hub: NI-DAQmx hub owning the card the slot pins live on.
            slots: Slot index to ``{pin, label}``, e.g. ``{0: {pin: ao6, label: GFP}}``.
            slot_count: Total slots; inferred from ``slots`` when None.
        """
        specs = {int(k): SlotSpec.model_validate(v) for k, v in slots.items()}
        ao = NiAnalogOutput(uid=f"{uid}_ao", hub=hub, ports={str(i): s.pin for i, s in specs.items()})
        super().__init__(
            uid=uid,
            ao_generator=ao,
            slots={i: s.label for i, s in specs.items()},
            slot_count=slot_count,
        )
