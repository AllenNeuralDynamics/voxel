"""What the operator edits: the profiles of an instrument and the rest of its saved state, in ``default.yaml`` and
``state.json``."""

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from itertools import pairwise, product
from typing import Annotated, Any, Literal, Self, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator
from pydantic_core import InitErrorDetails
from rigup.device import OperationRequest
from vxlib.issues import Problem, Problems
from vxlib.schema import FrozenModel, Key, UniqueList, identifier, repeated
from vxlib.units import Quantity

from vxl.devices.base import DeviceId
from vxl.instrument.config import InstrumentConfig, NotDefault
from vxl.instrument.samples import render
from vxl.instrument.signals import Timeline
from vxl.metadata import ExperimentMetadata, MetadataCls, get_path_from_class
from vxl.optics import AxisPosition, SpecimenAxis
from vxl.wiring import PinRef, Wire

ProfileId = Annotated[str, identifier("Profile id")]

PropertyName = Annotated[str, Field(min_length=1)]
"""The name of a property that a device class declares, such as ``exposure_time_ms``."""


ChannelName = Annotated[str, identifier("Channel name")]
"""The name of a channel of a profile, such as ``gfp``: what its cameras image."""

type ChannelCameras = Annotated[dict[DeviceId, DeviceId], Field(min_length=1)]
"""The cameras of 1 channel, each with the light it uses."""


type PowerMode = Literal["full", "dim"]
"""Which powers of a profile are in use."""


class Power(FrozenModel):
    """The power of 1 laser or modulator that software sets, in the device's own unit. ``dim`` is for a dim light: where
    there is none, the full power holds. Each is 1 power, or 1 for each position of ``router``, a device that sends the
    light a different way."""

    full: dict[str, Quantity] | Quantity
    dim: dict[str, Quantity] | Quantity | None = None
    router: DeviceId | None = None

    @model_validator(mode="after")
    def _positions_need_a_router(self) -> Self:
        if self.router is None and (isinstance(self.full, dict) or isinstance(self.dim, dict)):
            raise ValueError("a power for each position needs a router")
        return self

    def at(self, mode: PowerMode, position: str | None = None) -> Quantity | None:
        """The power in a power mode, with the router at ``position``. Where there is no dim power, the full one
        holds. ``None`` when there is no power for the position."""
        for level in (self.dim, self.full) if mode == "dim" else (self.full,):
            if not isinstance(level, dict):
                if level is not None:
                    return level
            elif position is not None and position in level:
                return level[position]
        return None

    def replace(self, mode: PowerMode, power: Quantity, position: str | None = None) -> Self:
        """A copy with ``power`` in a power mode. A power for each position changes only at ``position``, and a new dim
        power takes the shape of the full one. Raise ``ValueError`` when a power for each position gets no position."""
        level = self.full if mode == "full" or self.dim is None else self.dim
        if not isinstance(level, dict):
            return self.model_copy(update={mode: power})
        if position is None:
            raise ValueError(f"a power for each position of '{self.router}' needs a position")
        kept = level if mode == "full" or self.dim is not None else {}
        return self.model_copy(update={mode: {**kept, position: power}})

    def problems(self, lowest: Quantity, highest: Quantity) -> Problems:
        """The problems of the powers against the lowest and highest power of the device: each is in its unit and
        inside its range."""
        problems = Problems()
        for mode, level in (("full", self.full), ("dim", self.dim)):
            if level is None:
                continue
            for power in level.values() if isinstance(level, dict) else [level]:
                if power.unit != lowest.unit:
                    problems.add(
                        "profile.power.unit", f"It takes its power in {lowest.unit}, not in {power.unit}.", mode
                    )
                elif not lowest.number <= power.number <= highest.number:
                    can = f"{lowest.number:g}..{highest.number:g} {lowest.unit}"
                    problems.add("profile.power.out_of_range", f"It cannot do {power} (it can do {can}).", mode)
        return problems


class Profile(FrozenModel):
    """What is on at the same moment, and all that it needs to run. ``channels`` names each channel, with its cameras
    and the light each uses; a camera is in at most 1 channel. ``positions`` gives the position of each device that
    this profile sets, ``power`` the power of each laser and modulator that software sets, and ``timelines`` what each
    signal generator plays. A kind of instrument adds its own fields in a subclass."""

    channels: dict[ChannelName, ChannelCameras] = Field(min_length=1)
    positions: dict[DeviceId, AxisPosition] = Field(default_factory=dict)
    power: dict[DeviceId, Power] = Field(default_factory=dict)
    props: dict[DeviceId, dict[PropertyName, Any]] = Field(default_factory=dict)
    setup: dict[DeviceId, list[OperationRequest]] = Field(default_factory=dict)
    timelines: dict[DeviceId, Timeline] = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None

    def lights(self) -> dict[DeviceId, DeviceId]:
        """Each camera of the profile, with the light it uses."""
        return {camera: light for cameras in self.channels.values() for camera, light in cameras.items()}

    def live_inputs(self, config: InstrumentConfig) -> dict[PinRef, Wire]:
        """Each pin that gets a signal in this profile, with the wire that feeds it: a wire of a generator that has a
        signal in its timeline, and each wire of a camera of this profile or of a stage axis, which make their own
        pulses."""
        played = {generator: set(timeline.signals) for generator, timeline in self.timelines.items()}
        found: dict[PinRef, Wire] = {}
        for sender in (*played, *self.lights(), *config.stage.devices().values()):
            for name, wire in config.wiring.outputs(sender).items():
                if sender not in played or name in played[sender]:
                    found.update(dict.fromkeys(wire.to, Wire(sender, name, wire)))
        return found

    def path_nodes(self, config: InstrumentConfig) -> set[str]:
        """Every node on the light paths of the channels, on both sides of the specimen, with each device at any
        position."""
        nodes: set[str] = set()
        for camera, light in self.lights().items():
            optics = config.optics
            for path in (*optics.paths_from(light, {}), *optics.paths_to(camera, {})):
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
        problems += self._power_problems(config, nodes)
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

    def _power_problems(self, config: InstrumentConfig, nodes: set[str]) -> Problems:
        """The problems of the powers that the files alone show: each is for a device on the light paths whose power no
        wire sets, and each router sends the light of this profile a different way and has the positions that the powers
        name."""
        wired = {pin.device for pin, wire in self.live_inputs(config).items() if wire.config.kind == "analog"}
        routers = config.optics.routers()
        problems = Problems()
        for device, power in self.power.items():
            if device not in nodes or device not in config.all_devices:
                msg = f"'{device}' is not a device on the light paths of this profile's channels."
                problems.add("profile.power.unexpected", msg, "power", device)
            elif device in wired:
                msg = f"A wire sets the power of '{device}' in this profile. Change its signal in the timeline."
                problems.add("profile.power.wired", msg, "power", device)
            if (router := power.router) is None:
                continue
            if router not in routers or router not in nodes:
                msg = f"'{router}' does not send the light of this profile a different way at each position."
                problems.add("profile.power.not_a_choice", msg, "power", device, "router")
                continue
            for mode, level in (("full", power.full), ("dim", power.dim)):
                if isinstance(level, dict) and (unknown := sorted(set(level) - set(routers[router]))):
                    msg = f"'{router}' has no position {', '.join(unknown)} (it has {', '.join(routers[router])})."
                    problems.add("profile.power.no_such_position", msg, "power", device, mode)
        return problems

    def _channel_problems(self, config: InstrumentConfig) -> Problems:
        """The problems of the channels: a camera is in at most 1 channel, each names a camera and a light source,
        and the light can go from the source to the specimen and from the specimen to the camera, with each device at
        any position."""
        cameras, sources = config.optics.detectors(), config.optics.sources()
        problems = Problems()
        seen: set[DeviceId] = set()
        for name, channel in self.channels.items():
            for camera, light in channel.items():
                where = ("channels", name, camera)
                if camera in seen:
                    msg = f"'{camera}' is in more than 1 channel: image another channel on it in another profile."
                    problems.add("profile.channel.camera_repeated", msg, *where)
                elif camera not in cameras:
                    msg = f"'{camera}' is not a detector of 'optics': a detector gives 'width' and 'height'."
                    problems.add("profile.channel.not_detector", msg, *where)
                elif light not in sources:
                    msg = f"'{light}' is not a light source: a node of 'optics' sends light to it."
                    problems.add("profile.channel.not_source", msg, *where)
                elif not config.optics.paths_from(light, {}):
                    msg = f"No light path goes from '{light}' to the specimen."
                    problems.add("profile.channel.no_path", msg, *where)
                elif not config.optics.paths_to(camera, {}):
                    msg = f"No light path goes from the specimen to '{camera}'."
                    problems.add("profile.channel.no_path", msg, *where)
                seen.add(camera)
        return problems

    def _dark_problems(self, config: InstrumentConfig) -> Problems:
        """Each camera that gets no light with the positions of this profile. A device that this profile does not
        set can be at any position: the instrument can set it."""
        problems = Problems()
        for name, channel in self.channels.items():
            for camera, light in channel.items():
                if not config.optics.paths_from(light, self.positions):
                    msg = f"No light of '{light}' reaches the specimen with {self._given()}."
                elif not config.optics.paths_to(camera, self.positions):
                    msg = f"No light goes from the specimen to '{camera}' with {self._given()}."
                else:
                    continue
                problems.add("profile.channel.dark", msg, "channels", name, camera)
        return problems

    def _timeline_problems(self, config: InstrumentConfig) -> Problems:
        problems = Problems()
        for generator, timeline in self.timelines.items():
            if not (wires := config.wiring.outputs(generator)):
                msg = f"'{generator}' sends no wires in 'wiring', so it has nothing to play."
                problems.add("profile.timeline.no_wires", msg, "timelines", generator)
                continue
            found = timeline.problems(wires)
            if not found:  # the specimens of a wrong timeline would repeat its problems
                found = render(timeline, wires).problems
            problems += found.under("timelines", generator)
        return problems

    def _given(self) -> str:
        """The positions that this profile sets, as words."""
        return ", ".join(f"{device} at {value}" for device, value in self.positions.items()) or "no positions"


class ProfileFields(TypedDict, total=False):
    """The fields of a profile that an update may change, each one optional. A kind adds its own in a subclass."""

    label: str | None
    desc: str


TaskId = Annotated[str, identifier("Task id")]


class Task(FrozenModel):
    """1 entry in the plan: the profiles to image, and the metadata of the specimen. ``metadata`` has the form that
    the state's ``metadata_cls`` gives. A kind of instrument adds its own fields in a subclass."""

    id: Annotated[TaskId, Key]
    profiles: Annotated[UniqueList[ProfileId], Field(min_length=1)]
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskFields(TypedDict, total=False):
    """The fields of a task that an update may change, each one optional. A task keeps its ``id``, and its metadata
    changes on its own. A kind adds its own fields in a subclass."""

    profiles: UniqueList[ProfileId]


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

type _DevicePositions = Mapping[DeviceId, AxisPosition]


class InstrumentState(BaseModel, frozen=True):
    """What the operator edits. ``state.json`` and ``default.yaml`` have this form. A kind of
    instrument adds its own fields in a subclass. ``plan`` is the tasks to run, and ``metadata_cls`` the form of the
    metadata of each task. ``positions`` gives the position of each device that the instrument sets, the same for
    every profile: 1 position, or the rule by which the device follows the stage."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    metadata_cls: MetadataCls = Field(default=get_path_from_class(ExperimentMetadata), validate_default=True)
    profiles: Mapping[ProfileId, Profile] = Field(min_length=1)
    positions: dict[DeviceId, PositionRule] = Field(default_factory=dict)
    plan: Annotated[Sequence[Task], NotDefault] = Field(default_factory=list)

    @field_validator("plan")
    @classmethod
    def _check_plan(cls, plan: Sequence[Task], info: ValidationInfo) -> Sequence[Task]:
        if duplicates := repeated(task.id for task in plan):
            raise ValueError(f"task ids must be unique (repeated: {duplicates})")
        form = info.data.get("metadata_cls")  # missing when metadata_cls itself failed
        if form is None:
            return plan
        checked: list[Task] = []
        errors: list[InitErrorDetails] = []
        for index, task in enumerate(plan):
            try:
                checked.append(task.model_copy(update={"metadata": form.model_validate(task.metadata).model_dump()}))
            except ValidationError as error:
                for found in error.errors():
                    detail = InitErrorDetails(
                        type=found["type"], loc=(index, "metadata", *found["loc"]), input=found["input"]
                    )
                    if "ctx" in found:
                        detail["ctx"] = found["ctx"]
                    errors.append(detail)
        if errors:
            raise ValidationError.from_exception_data(cls.__name__, errors)
        return checked

    @classmethod
    def default_fields(cls) -> frozenset[str]:
        """The fields that can be saved as a default: those with no ``NotDefault`` mark."""
        return frozenset(name for name, field in cls.model_fields.items() if NotDefault not in field.metadata)

    def positions_at(self, stage: Mapping[SpecimenAxis, float], previous: _DevicePositions) -> _DevicePositions:
        """The position of each device in ``positions``, with the stage at ``stage``. ``previous`` gives the positions
        at the stop before, which a device that follows the stage keeps within its margin."""
        found: dict[DeviceId, AxisPosition] = {}
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
        for index, task in enumerate(self.plan):
            for profile_index, profile_id in enumerate(task.profiles):
                if profile_id not in self.profiles:
                    loc = ("plan", index, "profiles", profile_index)
                    problems.append(Problem.not_configured("Profile", profile_id, code="task.profile_missing", loc=loc))
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
        """Each camera of a profile gets 1 magnification from the parts between the specimen and the camera. A device
        that follows the stage is checked at each position of its rule."""
        problems = Problems()
        for profile_id, profile in self.profiles.items():
            messages: dict[DeviceId, str] = {}
            for held in self._held_positions():
                for camera in profile.lights():
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
            names = {camera: name for name, channel in profile.channels.items() for camera in channel}
            for camera, msg in messages.items():
                problems.add("profile.channel.magnification", msg, profile_id, "channels", names[camera], camera)
        return problems

    def _held_positions(self) -> list[dict[DeviceId, AxisPosition]]:
        """Each set of positions that the instrument can give its devices. A device that follows the stage takes
        each position of its rule."""
        choices: list[Sequence[AxisPosition]] = [
            position.order if isinstance(position, StageFollowRule) else [position]
            for position in self.positions.values()
        ]
        return [dict(zip(self.positions, chosen, strict=True)) for chosen in product(*choices)]
