"""What the operator edits: the profiles of an instrument and the rest of its saved state, in ``default.yaml`` and
``state.json``."""

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from itertools import pairwise, product
from typing import Annotated, Any, Self, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from rigup.device.results import CommandRequest
from vxlib.problems import Problems
from vxlib.schema import FrozenModel, UniqueList, identifier

from vxl.core.instrument.config import (
    AxisPosition,
    DeviceUid,
    InstrumentConfig,
    NotDefault,
    PinRef,
    SpecimenAxis,
    Wire,
)
from vxl.core.instrument.samples import render
from vxl.core.instrument.signals import Timeline
from vxl.devices.camera.roi import AreaROI
from vxl.metadata import ExperimentMetadata, MetadataCls

ProfileId = Annotated[str, identifier("Profile id")]

PropertyName = Annotated[str, Field(min_length=1)]
"""The name of a property that a device class declares, such as ``exposure_time_ms``."""


class Channel(FrozenModel):
    """What 1 camera images in a profile: its light source, and the sensor region that the camera reads out."""

    illumination: DeviceUid
    fov: AreaROI
    label: str | None = None


class Profile(FrozenModel):
    """What is on at the same moment, and all that it needs to run. ``channels`` has 1 entry for each camera that is
    on. ``positions`` gives the position of each device that this profile sets, and ``timelines`` what each signal
    generator plays. A kind of instrument adds its own fields in a subclass."""

    channels: dict[DeviceUid, Channel] = Field(min_length=1)
    positions: dict[DeviceUid, AxisPosition] = Field(default_factory=dict)
    props: dict[DeviceUid, dict[PropertyName, Any]] = Field(default_factory=dict)
    setup: dict[DeviceUid, list[CommandRequest]] = Field(default_factory=dict)
    timelines: dict[DeviceUid, Timeline] = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None

    def live_inputs(self, config: InstrumentConfig) -> dict[PinRef, Wire]:
        """Each pin that gets a signal in this profile, with the wire that feeds it: a wire of a generator that has a
        signal in its timeline, and each wire of a camera of this profile or of a stage axis, which make their own
        pulses."""
        played = {generator: set(timeline.signals) for generator, timeline in self.timelines.items()}
        found: dict[PinRef, Wire] = {}
        for sender in (*played, *self.channels, *config.stage.devices().values()):
            for name, wire in config.wiring.outputs(sender).items():
                if sender not in played or name in played[sender]:
                    found.update(dict.fromkeys(wire.to, Wire(sender, name, wire)))
        return found

    def path_nodes(self, config: InstrumentConfig) -> set[str]:
        """Every node on the light paths of the channels, on both sides of the sample, with each device at any
        position."""
        nodes: set[str] = set()
        for camera, channel in self.channels.items():
            optics = config.optics
            for path in (*optics.paths_from(channel.illumination, {}), *optics.paths_to(camera, {})):
                nodes.update(path.nodes)
        return nodes

    def problems(self, config: InstrumentConfig) -> Problems:
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
        return problems

    def _position_problems(self, config: InstrumentConfig, nodes: set[str]) -> Problems:
        """The problems of the positions: each names a device on the light paths."""
        elements = config.optics.elements()
        problems = Problems()
        for device in self.positions:
            if device not in nodes or device not in elements or device not in config.all_devices:
                msg = f"'{device}' is not a device on the light paths of this profile's channels."
                problems.add("profile.position.unexpected", msg, "positions", device)
        return problems

    def _channel_problems(self, config: InstrumentConfig) -> Problems:
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
            elif not config.optics.paths_from(channel.illumination, {}):
                msg = f"No light path goes from '{channel.illumination}' to the sample."
                problems.add("profile.channel.no_path", msg, "channels", camera)
            elif not config.optics.paths_to(camera, {}):
                msg = f"No light path goes from the sample to '{camera}'."
                problems.add("profile.channel.no_path", msg, "channels", camera)
        return problems

    def _dark_problems(self, config: InstrumentConfig) -> Problems:
        """Each camera that gets no light with the positions of this profile. A device that this profile does not
        set can be at any position: the instrument can set it."""
        problems = Problems()
        for camera, channel in self.channels.items():
            if not config.optics.paths_from(channel.illumination, self.positions):
                msg = f"No light of '{channel.illumination}' reaches the sample with {self._given()}."
            elif not config.optics.paths_to(camera, self.positions):
                msg = f"No light goes from the sample to '{camera}' with {self._given()}."
            else:
                continue
            problems.add("profile.channel.dark", msg, "channels", camera)
        return problems

    def _timeline_problems(self, config: InstrumentConfig) -> Problems:
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

type _DevicePositions = Mapping[DeviceUid, AxisPosition]


class InstrumentState(BaseModel, frozen=True):
    """What the operator edits. ``state.json`` has this form, and so do ``default.yaml`` and a preset. A kind of
    instrument adds its own fields in a subclass. ``metadata`` is the facts about the specimen, in the form that
    ``metadata_cls`` gives. ``positions`` gives the position of each device that the instrument sets, the same for
    every profile: 1 position, or the rule by which the device follows the stage."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    metadata_cls: MetadataCls = ExperimentMetadata
    metadata: Annotated[dict[str, Any], NotDefault] = Field(default_factory=dict, validate_default=True)
    profiles: Mapping[ProfileId, Profile] = Field(min_length=1)
    positions: dict[DeviceUid, PositionRule] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _check_metadata(cls, metadata: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        form = info.data.get("metadata_cls")  # missing when metadata_cls itself failed
        return metadata if form is None else form.model_validate(metadata).model_dump()

    @classmethod
    def default_fields(cls) -> frozenset[str]:
        """The fields that can be saved as a default: those with no ``NotDefault`` mark."""
        return frozenset(name for name, field in cls.model_fields.items() if NotDefault not in field.metadata)

    def positions_at(self, stage: Mapping[SpecimenAxis, float], previous: _DevicePositions) -> _DevicePositions:
        """The position of each device in ``positions``, with the stage at ``stage``. ``previous`` gives the positions
        at the stop before, which a device that follows the stage keeps within its margin."""
        found: _DevicePositions = {}
        for device, rule in self.positions.items():
            if isinstance(rule, StageFollowRule):
                before = previous.get(device)
                found[device] = rule.position(stage[rule.axis], previous=before if isinstance(before, str) else None)
            else:
                found[device] = rule
        return found

    def problems(self, config: InstrumentConfig) -> Problems:
        """Return the problems of this state against ``config``: those of its positions and of each profile. A kind
        of instrument adds its own."""
        problems = self._position_problems(config).under("positions")
        for profile_id, profile in self.profiles.items():
            problems += profile.problems(config).under("profiles", profile_id)
        problems += self._level_problems(config).under("profiles")
        problems += self._magnification_problems(config).under("profiles")
        return problems

    def _position_problems(self, config: InstrumentConfig) -> Problems:
        """The problems of the instrument's own positions: each names a device of the optical graph."""
        elements = config.optics.elements()
        problems = Problems()
        for device in self.positions:
            if device not in elements or device not in config.all_devices:
                problems.add("positions.unexpected", f"'{device}' is not a device of 'optics'.", device)
        return problems

    def _level_problems(self, config: InstrumentConfig) -> Problems:
        """The problems between the instrument's positions and those of the profiles. A device gets its position
        from 1 level only. A device that sends the light a different way at each position, on a profile's light
        paths, gets a position. A device that 1 profile sets, each profile with it on its light paths sets."""
        elements, routers = config.optics.elements(), config.optics.routers()
        in_a_profile = {device for profile in self.profiles.values() for device in profile.positions}
        problems = Problems()
        for profile_id, profile in self.profiles.items():
            nodes = profile.path_nodes(config)
            for device in profile.positions:
                if device in self.positions:
                    msg = f"'{device}' is set in the instrument's positions and in this profile. Set it in 1 place."
                    problems.add(
                        "profile.position.two_levels",
                        msg,
                        profile_id,
                        "positions",
                        device,
                    )
            for device in sorted(nodes):
                if device in self.positions or device in profile.positions or device not in elements:
                    continue
                if device in config.all_devices and device in routers:
                    msg = (
                        f"'{device}' is on the light paths of this profile, and no position is given. Give it here, "
                        "or in the instrument's positions."
                    )
                    code = "profile.position.missing"
                elif device in in_a_profile:
                    msg = f"A different profile sets '{device}', and it is on the light paths of this profile too."
                    code = "profile.position.not_in_all_profiles"
                else:
                    continue
                problems.add(code, msg, profile_id, "positions", device)
        return problems

    def _magnification_problems(self, config: InstrumentConfig) -> Problems:
        """Each camera of a profile gets 1 magnification from the parts between the sample and the camera. A device
        that follows the stage is checked at each position of its rule."""
        problems = Problems()
        for profile_id, profile in self.profiles.items():
            messages: dict[DeviceUid, str] = {}
            for held in self._held_positions():
                for camera in profile.channels:
                    where = {**held, **profile.positions}
                    found = [config.magnification(path, where) for path in config.optics.paths_to(camera, where)]
                    given = sorted({magnification for magnification in found if magnification is not None})
                    if any(magnification is None for magnification in found):
                        msg = f"A light path to '{camera}' has no part that gives a magnification."
                    elif len(given) > 1:
                        msg = f"The light paths to '{camera}' give more than 1 magnification: {given}."
                    else:
                        continue
                    messages.setdefault(camera, msg)
            for camera, msg in messages.items():
                problems.add("profile.channel.magnification", msg, profile_id, "channels", camera)
        return problems

    def _held_positions(self) -> list[dict[DeviceUid, AxisPosition]]:
        """Each set of positions that the instrument can give its devices. A device that follows the stage takes
        each position of its rule."""
        choices: list[Sequence[AxisPosition]] = [
            position.order if isinstance(position, StageFollowRule) else [position]
            for position in self.positions.values()
        ]
        return [dict(zip(self.positions, chosen, strict=True)) for chosen in product(*choices)]
