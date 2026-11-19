"""The files of a SPIM instrument: ``rig.yaml``, ``default.yaml``, ``state.json`` and presets."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import Field, PositiveFloat, model_validator
from vxlib.issues import Problem, Problems
from vxlib.schema import FrozenModel
from vxlib.units import Portion

from vxl.devices.camera import AreaROI
from vxl.station.instrument.config import (
    DeviceUid,
    DigitalWire,
    InstrumentConfig,
    SpecimenAxis,
    Stage,
    Wire,
)
from vxl.station.instrument.state import Profile

SOFTWARE = "software"
"""The pacer of a capture that the program runs frame by frame."""

type Motion = Literal["step", "sweep"]
"""``step``: move, stop, take the frame. ``sweep``: take frames while moving."""


class Scan(FrozenModel):
    """How 1 capture runs. ``axis`` is the stage axis that it moves; the other 2 are tiled. ``pacer`` is the device
    whose own clock or pulses set the rhythm, or ``software``. ``margin`` is how much slower a sweep runs than
    spacing ÷ frame time, so that no pulse of the stage comes before a frame ends."""

    axis: SpecimenAxis
    motion: Motion
    pacer: DeviceUid | Literal["software"]
    margin: Portion | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.motion == "step" and self.margin is not None:
            raise ValueError("'margin' is for a sweep; a step has none")
        if self.motion == "sweep" and self.pacer == SOFTWARE:
            raise ValueError("the program can pace a step, not a sweep")
        return self

    def tiled(self) -> list[SpecimenAxis]:
        """The stage axes that a capture does not move."""
        return [axis for axis in Stage.axes() if axis != self.axis]

    def view(self) -> tuple[SpecimenAxis, SpecimenAxis]:
        """The 2 axes of the view in which people first draw a region: the top for a Z scan, and otherwise the side
        that shows the scan axis and Z."""
        return ("x", "y") if self.axis == "z" else (self.axis, "z")


@dataclass(frozen=True)
class TriggerChain:
    """What starts each device of 1 profile in 1 capture. ``starters`` start by themselves: the pacer, or every
    generator when the program paces. ``waits`` gives the wire whose pulses start each other device. ``unstarted``
    lists each camera, generator or stepping axis that nothing starts."""

    starters: tuple[DeviceUid, ...]
    waits: Mapping[DeviceUid, Wire]
    unstarted: tuple[DeviceUid, ...]


class SPIMConfig(InstrumentConfig, frozen=True):
    """The ``rig.yaml`` of a SPIM instrument. ``scan`` says how 1 capture runs."""

    scan: Scan

    def problems(self) -> Problems:
        problems = super().problems()
        problems += self._software_problems()
        problems += self._scan_problems().under("scan")
        return problems

    def _software_problems(self) -> Problems:
        problems = Problems()
        if SOFTWARE in self.all_devices or SOFTWARE in self.parts:
            msg = "'software' names the program as the pacer of a scan, so no device takes it."
            problems.add("rig.reserved_name", msg, *self.component_location(SOFTWARE))
        return problems

    def _scan_problems(self) -> Problems:
        problems = Problems()
        pacer = self.scan.pacer
        if pacer != SOFTWARE and pacer not in self.all_devices:
            problems.append(Problem.not_configured("Device", pacer, code="rig.scan.pacer_missing", loc=("pacer",)))
        return problems


class SPIMProfile(Profile):
    """The profile of a SPIM instrument. ``spacing`` gives the µm between frames along the scan axis. ``fov`` gives
    the sensor region that a channel's camera reads out; a camera that it leaves out reads its whole sensor."""

    spacing: PositiveFloat
    fov: dict[DeviceUid, AreaROI] = Field(default_factory=dict)

    def problems(self, config: InstrumentConfig) -> Problems:
        if not isinstance(config, SPIMConfig):
            raise TypeError(f"a SPIMProfile is for a SPIMConfig, not a {type(config).__name__}")
        problems = super().problems(config)
        for camera in self.fov.keys() - self.lights().keys():
            msg = f"'{camera}' has a region in 'fov' but is not a channel of the profile."
            problems.add("profile.fov.not_channel", msg, "fov", camera)
        if not self._channel_problems(config):  # a wrong channel would repeat as the problems of the chain
            problems += self._chain_problems(config)
        return problems

    def trigger_chain(self, config: SPIMConfig) -> TriggerChain:
        """What starts each device of this profile in 1 capture, worked out from ``scan`` and the wires that carry a
        signal. Follow those digital wires from the pacer. Each camera, generator, or axis that steps waits on the
        first one that reaches it. A starter never waits, an axis that sweeps never waits, and with ``software`` the
        program moves the axis. A wire to any other device, such as a laser's gate, starts nothing."""
        by_program = config.scan.pacer == SOFTWARE
        waiting = {*self.lights(), *self.timelines}
        if config.scan.motion == "step" and not by_program:
            waiting.add(config.stage.device(config.scan.axis))
        starters = tuple(sorted(self.timelines)) if by_program else (config.scan.pacer,)
        pulses = [(pin, wire) for pin, wire in self.live_inputs(config).items() if isinstance(wire.config, DigitalWire)]

        waits: dict[DeviceUid, Wire] = {}
        reached, pending = set(starters), list(starters)
        while pending:
            sender = pending.pop(0)
            for pin, wire in pulses:
                if wire.sender == sender and pin.device in waiting and pin.device not in reached:
                    waits[pin.device] = wire
                    reached.add(pin.device)
                    pending.append(pin.device)
        return TriggerChain(starters=starters, waits=waits, unstarted=tuple(sorted(waiting - reached)))

    def _chain_problems(self, config: SPIMConfig) -> Problems:
        """Each device of this profile that nothing starts. When wires reach it and none carries a signal, the
        problem is the signal that this profile does not play."""
        problems = Problems()
        if config.scan.pacer != SOFTWARE and config.scan.pacer not in config.all_devices:
            return problems
        live = self.live_inputs(config)
        for device in self.trigger_chain(config).unstarted:
            reaching = [
                (sender, name, any(pin in live for pin in wire.to if pin.device == device))
                for sender, wires in config.wiring.root.items()
                for name, wire in wires.items()
                if isinstance(wire, DigitalWire) and any(pin.device == device for pin in wire.to)
            ]
            if reaching and not any(carries for _, _, carries in reaching):
                sender, name, _ = reaching[0]
                msg = f"'{device}' waits on {sender}'s {name}, and this profile plays no signal on it."
                problems.add("profile.trigger_not_played", msg, "timelines", sender)
            else:
                msg = f"Nothing starts '{device}': no wire in the chain from the pacer reaches it."
                problems.add("profile.unstarted", msg)
        return problems
