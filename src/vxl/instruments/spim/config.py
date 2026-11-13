"""The files of a SPIM instrument: ``rig.yaml``, ``default.yaml``, ``state.json`` and presets."""

from bisect import bisect_right
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Annotated, Any, Literal, Self, TypedDict

from pydantic import Field, PositiveFloat, model_validator
from rigup.device.schema import CommandRequest
from vxlib.problems import Problem, Problems
from vxlib.schema import FrozenModel, UniqueList, identifier
from vxlib.units import Portion

from vxl.core.instrument.config import (
    AxisPosition,
    DeviceUid,
    DigitalWire,
    InstrumentConfig,
    SpecimenAxis,
    Stage,
    Wire,
)
from vxl.core.instrument.samples import render
from vxl.core.instrument.signals import Timeline
from vxl.devices.camera.roi import AreaROI

ProfileId = Annotated[str, identifier("Profile id")]

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

    def trigger_chain(self, cameras: Collection[DeviceUid], generators: Collection[DeviceUid]) -> TriggerChain:
        """What starts each device in 1 capture with ``cameras`` and ``generators``, worked out from ``scan`` and the
        wires. Follow the digital wires from the pacer. Each camera, generator, or axis that steps waits on the first
        wire that reaches it. A starter never waits, an axis that sweeps never waits, and with ``software`` the
        program moves the axis. A wire to any other device, such as a laser's gate, starts nothing."""
        by_program = self.scan.pacer == SOFTWARE
        waiting = {*cameras, *generators}
        if self.scan.motion == "step" and not by_program:
            waiting.add(self.stage.device(self.scan.axis))
        starters = tuple(sorted(generators)) if by_program else (self.scan.pacer,)

        waits: dict[DeviceUid, Wire] = {}
        reached, pending = set(starters), list(starters)
        while pending:
            sender = pending.pop(0)
            for name, config in self.wiring.outputs(sender).items():
                if not isinstance(config, DigitalWire):
                    continue
                for pin in config.to:
                    if pin.device in waiting and pin.device not in reached:
                        waits[pin.device] = Wire(sender, name, config)
                        reached.add(pin.device)
                        pending.append(pin.device)
        return TriggerChain(starters=starters, waits=waits, unstarted=tuple(sorted(waiting - reached)))

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


PropertyName = Annotated[str, Field(min_length=1)]
"""The name of a property that a device class declares, such as ``exposure_time_ms``."""


class Channel(FrozenModel):
    """What 1 camera images in a profile: its light source, and the sensor region that the camera reads out."""

    illumination: DeviceUid
    fov: AreaROI
    label: str | None = None


class Profile(FrozenModel):
    """What is on at the same moment, and all that it needs to run. ``channels`` has 1 entry for each camera that is
    on. ``positions`` gives the position of each device that this profile sets. ``timelines`` gives what each signal
    generator plays, and ``spacing`` the µm between frames along the scan axis."""

    channels: dict[DeviceUid, Channel] = Field(min_length=1)
    positions: dict[DeviceUid, AxisPosition] = Field(default_factory=dict)
    props: dict[DeviceUid, dict[PropertyName, Any]] = Field(default_factory=dict)
    setup: dict[DeviceUid, list[CommandRequest]] = Field(default_factory=dict)
    timelines: dict[DeviceUid, Timeline] = Field(default_factory=dict)
    spacing: PositiveFloat
    desc: str = ""
    label: str | None = None

    def problems(self, config: SPIMConfig) -> Problems:
        """Return the problems of this profile against ``config``."""
        problems = self._channel_problems(config)
        if problems:  # the checks below read the light paths, so a wrong channel would repeat as their problems
            problems += self._timeline_problems(config)
            return problems
        nodes = self.path_nodes(config)

        positions = self._position_problems(config, nodes)
        problems += positions
        if not positions:
            problems += self._dark_problems(config)

        for device in self.props:
            if device in nodes and device in config.all_devices:
                continue
            if device not in nodes:
                msg = f"'{device}' is not on the light paths of this profile's channels."
            else:
                msg = f"'{device}' is a part, so it has no settings."
            problems.add("profile.props_inactive", msg, "props", device)
        for device in self.setup:
            if device not in nodes or device not in config.all_devices:
                msg = f"'{device}' is not a device on the light paths of this profile's channels."
                problems.add("profile.setup_inactive", msg, "setup", device)
        problems += self._timeline_problems(config)
        problems += self._chain_problems(config)
        return problems

    def path_nodes(self, config: SPIMConfig) -> set[str]:
        """Every node on the light paths of the channels, on both sides of the sample, with each device at any
        position."""
        nodes: set[str] = set()
        for camera, channel in self.channels.items():
            for path in (
                *config.illumination_paths(channel.illumination, {}),
                *config.detection_paths(camera, {}),
            ):
                nodes.update(path.nodes)
        return nodes

    def _position_problems(self, config: SPIMConfig, nodes: set[str]) -> Problems:
        """The problems of the positions: each names a device on the light paths."""
        elements = config.optics.elements()
        problems = Problems()
        for device in self.positions:
            if device not in nodes or device not in elements or device not in config.all_devices:
                msg = f"'{device}' is not a device on the light paths of this profile's channels."
                problems.add("profile.position.unexpected", msg, "positions", device)
        return problems

    def _channel_problems(self, config: SPIMConfig) -> Problems:
        """The problems of the channels: each names a camera and a light source, and the light can go from the
        source to the sample and from the sample to the camera, with each device at any position."""
        cameras, sources = config.optics.detectors(), config.optics.sources()
        problems = Problems()
        for camera, channel in self.channels.items():
            if camera not in cameras:
                msg = f"'{camera}' is not a detector of 'optics': a detector gives 'width' and 'height'."
                problems.add("profile.channel.not_detector", msg, "channels", camera)
            elif channel.illumination not in sources:
                msg = f"'{channel.illumination}' is not a light source: a node of 'optics' sends light to it."
                problems.add(
                    "profile.channel.not_source",
                    msg,
                    "channels",
                    camera,
                    "illumination",
                )
            elif not config.illumination_paths(channel.illumination, {}):
                msg = f"No light path goes from '{channel.illumination}' to the sample."
                problems.add("profile.channel.no_path", msg, "channels", camera)
            elif not config.detection_paths(camera, {}):
                msg = f"No light path goes from the sample to '{camera}'."
                problems.add("profile.channel.no_path", msg, "channels", camera)
        return problems

    def _dark_problems(self, config: SPIMConfig) -> Problems:
        """Each camera that gets no light with the positions of this profile. A device that this profile does not
        set can be at any position: the instrument can set it."""
        problems = Problems()
        for camera, channel in self.channels.items():
            if not config.illumination_paths(channel.illumination, self.positions):
                msg = f"No light of '{channel.illumination}' reaches the sample with {self._given()}."
            elif not config.detection_paths(camera, self.positions):
                msg = f"No light goes from the sample to '{camera}' with {self._given()}."
            else:
                continue
            problems.add("profile.channel.dark", msg, "channels", camera)
        return problems

    def _timeline_problems(self, config: SPIMConfig) -> Problems:
        problems = Problems()
        for generator, timeline in self.timelines.items():
            if not (wires := config.wiring.outputs(generator)):
                msg = f"'{generator}' sends no wires in 'wiring', so it has nothing to play."
                problems.add("profile.timeline.no_wires", msg, "timelines", generator)
                continue
            found = timeline.problems(wires)
            if not found:  # the samples of a wrong timeline would repeat its problems
                found = render(timeline, wires).problems
            problems += found.under("timelines", generator)
        return problems

    def _chain_problems(self, config: SPIMConfig) -> Problems:
        """Each device of this profile that nothing starts, and each device that waits on a wire with no pulses. A
        stage axis or a camera makes the pulses of its own wires. The profile must play a signal on any other wire."""
        problems = Problems()
        if config.scan.pacer != SOFTWARE and config.scan.pacer not in config.all_devices:
            return problems
        chain = config.trigger_chain(self.channels, self.timelines)
        for device in chain.unstarted:
            msg = f"Nothing starts '{device}': no wire in the chain from the pacer reaches it."
            problems.add("profile.unstarted", msg)
        own_pulses = {*config.stage.devices().values(), *config.optics.detectors()}
        for device, wire in chain.waits.items():
            if wire.sender in own_pulses:
                continue
            timeline = self.timelines.get(wire.sender)
            if timeline is None or wire.name not in timeline.signals:
                msg = f"'{device}' waits on {wire.sender}'s {wire.name}, and this profile plays no signal on it."
                problems.add("profile.trigger_not_played", msg, "timelines", wire.sender)
        return problems

    def _given(self) -> str:
        """The positions that this profile sets, as words."""
        return ", ".join(f"{device} at {value}" for device, value in self.positions.items()) or "no positions"


class ProfileDetails(TypedDict, total=False):
    """The names and notes of a profile, each one optional. ``channel_labels`` gives the label of each camera's
    channel."""

    label: str | None
    desc: str
    channel_labels: dict[DeviceUid, str | None]


class StageFollowRule(FrozenModel):
    """A device follows the stage. Along ``axis``, it takes the positions in ``order``, 1 after the other. ``at``
    gives the points, in µm, where it changes to the next position; within ``margin`` of a point, it keeps the
    position it has."""

    axis: SpecimenAxis
    order: Annotated[UniqueList[str], Field(min_length=2)]
    at: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(min_length=1)
    margin: float = Field(default=0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if any(b <= a for a, b in pairwise(self.at)):
            raise ValueError("'at' must rise from 1 point to the next")
        if len(self.at) != len(self.order) - 1:
            points = len(self.order) - 1
            raise ValueError(f"{len(self.order)} positions in 'order' need {points} in 'at', got {len(self.at)}")
        return self

    def position(self, coordinate: float, *, previous: str | None = None) -> str:
        """The position at ``coordinate`` on ``axis``. Next to ``previous``, it stays there until ``coordinate``
        passes the point between them by the margin."""
        index = bisect_right(self.at, coordinate)
        if previous in self.order and abs(index - (before := self.order.index(previous))) == 1:
            point = self.at[min(index, before)]
            stays = coordinate < point + self.margin if index > before else coordinate >= point - self.margin
            if stays:
                index = before
        return self.order[index]


type PositionRule = AxisPosition | StageFollowRule
"""How a device gets its position for every profile: always 1 position, or by following the stage."""
