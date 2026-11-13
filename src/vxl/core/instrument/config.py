"""The files of an instrument: ``rig.yaml``, ``default.yaml`` and ``state.json``."""

import math
import secrets
from abc import abstractmethod
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Annotated, Any, Literal, NamedTuple, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    PlainSerializer,
    RootModel,
    Tag,
    ValidationInfo,
    field_validator,
    model_validator,
)
from rigup.config import RigConfig
from vxlib.problems import KeyPath, Problem, Problems
from vxlib.schema import FrozenModel, UniqueList, check_identifier, identifier
from vxlib.units import Quantity, Time, Voltage
from vxlib.vector import Span, Vec3D

from rigup import Part
from vxl.metadata import ExperimentMetadata, MetadataCls
from vxl.parts import Filter, Objective

_ID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
"""Crockford's base32 in lowercase: digits and letters without i, l, o and u, which are easy to misread."""

InstrumentId = Annotated[str, Field(pattern=f"^[0-7][{_ID_ALPHABET}]{{25}}$")]
"""128 random bits in 26 characters, safe in URLs and file names."""

InstrumentName = Annotated[str, Field(min_length=1, max_length=32)]
"""A label for people."""

InstrumentModel = Annotated[str, Field(min_length=1, max_length=64)]
"""The lab's own label for the kind of instrument, such as ``exaSPIM`` or ``exaspim.v2``."""

InstrumentTarget = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")]
"""The class that runs the instrument, as a dotted path such as ``vxl.instruments.spim.Microscope``."""

DeviceUid = Annotated[str, identifier("Device UID")]
"""The name of a device of the rig."""

type AxisPosition = Annotated[float, Field(allow_inf_nan=False)] | str
"""Where an axis is: a number, or the name of a position for an axis that has named positions."""


def new_instrument_id() -> str:
    value = secrets.randbits(128)
    return "".join(_ID_ALPHABET[(value >> shift) & 31] for shift in range(125, -1, -5))


class _NotDefault:
    def __repr__(self) -> str:
        return "NotDefault"


NotDefault = _NotDefault()
"""The mark of a state field that is about the specimen on the stage, and not about the instrument. Such a field is
never saved as a default: ``plan: Annotated[list[Task], NotDefault]``."""


# === Stage and Specimen space ===

type SpecimenAxis = Literal["x", "y", "z"]


type _SpecimenDirection = dict[SpecimenAxis, float]
"""A direction in the specimen's axes, such as ``{x: 1, z: 1}``. Only the direction counts, not the length."""


class Stage(FrozenModel):
    """The device that drives each specimen axis."""

    x: DeviceUid
    y: DeviceUid
    z: DeviceUid

    @staticmethod
    def axes() -> tuple[SpecimenAxis, ...]:
        """The specimen axes, in order."""
        return ("x", "y", "z")

    def device(self, axis: SpecimenAxis) -> DeviceUid:
        return getattr(self, axis)

    def devices(self) -> dict[SpecimenAxis, DeviceUid]:
        """The device of each axis."""
        return {axis: self.device(axis) for axis in self.axes()}


# === Wiring ===

WireName = Annotated[str, identifier("Wire name")]

_Connector = Annotated[str, identifier("Connector")]
"""A connector, named as it is on the hardware."""


class Pin(NamedTuple):
    """A connector of a device or a part, written ``camera/trigger_in``."""

    device: str
    connector: str

    def __str__(self) -> str:
        return f"{self.device}/{self.connector}"

    @staticmethod
    def parse(value: Any) -> Any:
        """Read a pin from its written form. A value that is not text is returned as it is."""
        if not isinstance(value, str):
            return value
        device, sep, connector = value.partition("/")
        if not sep or "/" in connector:
            raise ValueError(f"a pin is written 'device/connector', got {value!r}")
        return Pin(check_identifier(device, "Device UID"), check_identifier(connector, "Connector"))


_Pins = UniqueList[Annotated[Pin, BeforeValidator(Pin.parse), PlainSerializer(str, return_type=str)]]
"""The pins a wire reaches, each once."""


_UnitName = Annotated[str, Field(min_length=1)]
"""The name of a unit, such as ``V``, ``mm`` or ``deg``."""


class DigitalWire(FrozenModel):
    """A wire that is on or off. ``off`` and ``on`` are given only when the sending pin is analog; the times are the
    shortest pulse, gap and period the receiver accepts."""

    pin: _Connector
    to: _Pins
    kind: Literal["digital"]
    off: Voltage | None = None
    on: Voltage | None = None
    on_time: Time | None = None
    off_time: Time | None = None
    repeat_time: Time | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.off is None) != (self.on is None):
            raise ValueError("give both 'off' and 'on', or neither")
        if self.off is not None and self.off == self.on:
            raise ValueError("'off' and 'on' must differ")
        for name in ("on_time", "off_time", "repeat_time"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"'{name}' must be greater than 0")
        return self


class AnalogWire(FrozenModel):
    """A wire that carries a value in its own ``unit``. ``scales`` lead from that unit down to volts, 1 table
    per step, such as ``{mm: {mm: [...], deg: [...]}, deg: {deg: [...], V: [...]}}``. ``limits`` may use any unit on
    that path. ``park`` is where the wire stays when no signal plays on it."""

    pin: _Connector
    to: _Pins
    kind: Literal["analog"]
    unit: _UnitName = "V"
    scales: dict[_UnitName, dict[_UnitName, list[float]]] = Field(default_factory=dict)
    limits: dict[_UnitName, Span] = Field(default_factory=dict)
    park: Quantity
    travel_time: Time | None = None
    jerk_time: Time | None = None

    @property
    def units(self) -> list[_UnitName]:
        """The units a value passes through, from the wire's unit down to V."""
        path = [self.unit]
        while path[-1] != "V" and path[-1] in self.scales:
            below = next(key for key in self.scales[path[-1]] if key != path[-1])
            if below in path:
                break
            path.append(below)
        return path

    @model_validator(mode="after")
    def _check(self) -> Self:
        for unit, table in self.scales.items():
            self._check_scale(unit, table)
        path = self.units
        if path[-1] != "V":
            raise ValueError(f"scales must lead from '{self.unit}' down to 'V' (they stop at '{path[-1]}')")
        if unused := sorted(set(self.scales) - set(path)):
            raise ValueError(f"scales for {unused} are not on the path from '{self.unit}' to 'V'")
        for unit, limits in self.limits.items():
            if unit not in path:
                raise ValueError(f"limits in '{unit}' are not on the path {path}")
            if limits.length == 0:
                raise ValueError(f"limits in '{unit}' need 2 different numbers, got {list(limits)}")
        self._check_park(self.park)
        if self.travel_time is not None and self.travel_time <= 0:
            raise ValueError("'travel_time' must be greater than 0")
        if self.travel_time is not None and self.unit not in self.limits:
            raise ValueError(f"'travel_time' is the time to cross the limits, so it needs limits in '{self.unit}'")
        if self.jerk_time is not None:
            if self.travel_time is None:
                raise ValueError("'jerk_time' needs 'travel_time'")
            if self.jerk_time <= 0:
                raise ValueError("'jerk_time' must be greater than 0")
        return self

    def _check_park(self, park: Quantity) -> None:
        if park.unit != self.unit:
            raise ValueError(f"park is in {park.unit}; this wire's unit is {self.unit}")
        if self.unit in self.limits:
            limits = self.limits[self.unit]
            if not limits.low <= park <= limits.high:
                raise ValueError(f"park {park} is outside the limits [{limits.low}, {limits.high}] {self.unit}")

    @staticmethod
    def _check_scale(unit: str, table: Mapping[str, list[float]]) -> None:
        if unit == "V":
            raise ValueError("'V' needs no scale")
        if unit not in table or len(table) != 2:
            raise ValueError(f"the scale for '{unit}' needs 2 columns: '{unit}' and the unit below it")
        columns = list(table.values())
        if len(columns[0]) != len(columns[1]) or len(columns[0]) < 2:
            raise ValueError(f"the columns of the scale for '{unit}' need the same length, at least 2")
        for name, column in table.items():
            steps = [b - a for a, b in pairwise(column)]
            if not (all(step > 0 for step in steps) or all(step < 0 for step in steps)):
                raise ValueError(f"column '{name}' of the scale for '{unit}' must rise or fall at every row")


type WireConfig = Annotated[DigitalWire | AnalogWire, Field(discriminator="kind")]


@dataclass(frozen=True)
class Wire:
    """1 wire, with the device that sends it."""

    sender: str
    name: str
    config: DigitalWire | AnalogWire

    def inputs_on(self, device: str) -> list[str]:
        """The connectors of ``device`` that this wire reaches, such as ``PFI0``."""
        return [pin.connector for pin in self.config.to if pin.device == device]


class Wiring(RootModel[dict[DeviceUid, dict[WireName, WireConfig]]]):
    """``wiring``: each sending device's wires, by name."""

    model_config = ConfigDict(frozen=True)

    def outputs(self, device: str) -> dict[WireName, DigitalWire | AnalogWire]:
        """Every wire that ``device`` sends, by name."""
        return dict(self.root.get(device, {}))

    def problems(self, *, devices: Collection[str], parts: Collection[str]) -> Problems:
        """Return the problems of the wiring that the file alone shows."""
        problems = Problems()
        owner: dict[str, tuple[str, str]] = {}

        def claim(pin: str, sender: str, name: str, pin_loc: KeyPath) -> None:
            if pin in owner:
                first_sender, first_name = owner[pin]
                msg = f"Pin '{pin}' is already in wire '{first_sender}.{first_name}'."
                problems.add("rig.wiring.pin_shared", msg, *pin_loc)
            else:
                owner[pin] = (sender, name)

        for sender, group in self.root.items():
            if sender not in devices:
                problems.append(
                    Problem.not_configured("Device", sender, code="rig.wiring.device_missing", loc=(sender,))
                )
                continue
            for name, wire in group.items():
                wire_loc = (sender, name)
                claim(f"{sender}/{wire.pin}", sender, name, (*wire_loc, "pin"))
                for index, pin in enumerate(wire.to):
                    if pin.device not in devices and pin.device not in parts:
                        msg = f"'{pin.device}' is not a device or a part; declare a part in 'parts'."
                        problems.add("rig.wiring.receiver_missing", msg, *wire_loc, "to", index)
                    else:
                        claim(str(pin), sender, name, (*wire_loc, "to", index))
        return problems


# === Optics ===

OpticalNodeName = Annotated[str, identifier("Optical node")]
"""A node of the optical graph: a device, a part, or ``sample``."""

_SAMPLE = "sample"
"""The node where the light meets the sample."""


_NodeList = Annotated[UniqueList[OpticalNodeName], Field(min_length=2)]
"""Several nodes that get the light at once."""


class Detector(FrozenModel):
    """A node where the light ends: a camera. ``width`` and ``height`` are the directions of the sides of its frame,
    at 90° to each other."""

    width: _SpecimenDirection
    height: _SpecimenDirection

    @field_validator("width", "height")
    @classmethod
    def _check_direction(cls, value: _SpecimenDirection) -> _SpecimenDirection:
        if not value:
            raise ValueError("a direction needs at least 1 axis")
        if not all(math.isfinite(number) for number in value.values()):
            raise ValueError("direction values must be finite")
        if math.hypot(*value.values()) == 0:
            raise ValueError("a direction cannot be all zeros")
        return value

    @model_validator(mode="after")
    def _check_right_angle(self) -> Self:
        _right_angle_tolerance = math.sin(math.radians(0.1))
        a, b = self.sides()
        cosine = a.x * b.x + a.y * b.y + a.z * b.z
        if abs(cosine) > _right_angle_tolerance:
            angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
            raise ValueError(f"'width' and 'height' must be at 90° to each other (they are at {angle:.2f}°)")
        return self

    def sides(self) -> tuple[Vec3D, Vec3D]:
        """The vectors of length 1 along the width and the height of a frame."""

        def unit(direction: _SpecimenDirection) -> Vec3D:
            vector = Vec3D(x=direction.get("x", 0.0), y=direction.get("y", 0.0), z=direction.get("z", 0.0))
            return vector / math.hypot(*vector)

        return unit(self.width), unit(self.height)


class OpticalElement(FrozenModel):
    """A node that sends the light on: a device, a part, or ``sample``. ``to`` says where the light goes next: 1
    node, or several at once. A device that sends the light a different way at each of its positions gives the node
    for each position. At a position that it leaves out, the light stops."""

    to: OpticalNodeName | _NodeList | Annotated[dict[str, OpticalNodeName | _NodeList], Field(min_length=1)]

    def ways(self) -> dict[str | None, list[OpticalNodeName]]:
        """The nodes that the light goes to, for each position. The key is ``None`` when the position does not
        change where the light goes."""
        ways = self.to.items() if isinstance(self.to, dict) else [(None, self.to)]
        return {label: [way] if isinstance(way, str) else list(way) for label, way in ways}


def _node_kind(node: object) -> str:
    if isinstance(node, Mapping):
        return "detector" if "width" in node or "height" in node else "element"
    return "detector" if isinstance(node, Detector) else "element"


type OpticalNode = Annotated[
    Annotated[Detector, Tag("detector")] | Annotated[OpticalElement, Tag("element")], Discriminator(_node_kind)
]
"""1 node of the optical graph. A node that gives ``width`` or ``height`` is a detector."""


class OpticalGraph(RootModel[dict[OpticalNodeName, OpticalNode]]):
    """``optics``: each node, by name."""

    model_config = ConfigDict(frozen=True)

    def elements(self) -> dict[OpticalNodeName, OpticalElement]:
        """The nodes that send the light on."""
        return {name: node for name, node in self.root.items() if isinstance(node, OpticalElement)}

    def detectors(self) -> dict[OpticalNodeName, Detector]:
        """The nodes where the light ends."""
        return {name: node for name, node in self.root.items() if isinstance(node, Detector)}

    def sources(self) -> dict[OpticalNodeName, OpticalElement]:
        """The nodes that nothing sends light to."""
        elements = self.elements()
        lit = {target for node in elements.values() for targets in node.ways().values() for target in targets}
        return {name: node for name, node in elements.items() if name not in lit and name != _SAMPLE}

    def problems(
        self,
        *,
        devices: Collection[str],
        parts: Collection[str],
    ) -> Problems:
        """Return the problems of the optical graph that the file alone shows."""
        problems = Problems()
        if _SAMPLE not in self.elements():
            msg = "The optical graph needs a 'sample' node with 'to': where the light goes on."
            problems.add("rig.optics.sample_missing", msg)
        for name, node in self.root.items():
            is_device = name in devices
            if name != _SAMPLE and not is_device and name not in parts:
                msg = f"'{name}' is not a device or a part; declare it in 'parts'."
                problems.add("rig.optics.node_unknown", msg, name)
            if isinstance(node, Detector):
                if not is_device:
                    msg = f"'{name}' is a detector, and a detector is a device."
                    problems.add("rig.optics.detector_not_device", msg, name)
                continue
            for label, targets in node.ways().items():
                for target in targets:
                    if target not in self.root:
                        place = ("to",) if label is None else ("to", label)
                        msg = f"'{target}' is not a node of 'optics'."
                        problems.add("rig.optics.target_missing", msg, name, *place)
        return problems


# === Instrument config ===


@dataclass(frozen=True)
class LightPath:
    """1 way the light goes on 1 side of the sample: from a source to the sample, or from the sample to a detector.
    ``magnification`` and ``band`` come from the parts that the light passes, in nm for the band, and are ``None``
    when no part gives one."""

    nodes: tuple[OpticalNodeName, ...]
    magnification: float | None
    band: tuple[float | None, float | None] | None


class InstrumentConfig(RigConfig, frozen=True):
    """An instrument's ``rig.yaml``: who the instrument is and what is on its bench. The ID is made when the
    instrument is created and never changes. ``target`` names the class that runs the instrument. The parts of the
    rig give the light path its facts: a :class:`~vxl.parts.Filter` its band, an :class:`~vxl.parts.Objective`
    its magnification. ``autosave``
    names, for each device, the properties that a change by a person saves in the active profile: a list of
    names, or ``*`` for each property that can be written."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: InstrumentId
    name: InstrumentName
    model: InstrumentModel | None = None
    target: InstrumentTarget
    stage: Stage
    wiring: Wiring = Field(default_factory=lambda: Wiring({}))
    optics: OpticalGraph
    autosave: dict[DeviceUid, Literal["*"] | list[str]] = Field(default_factory=dict)

    def problems(self) -> Problems:
        """Return the problems of the bench that the file shows."""
        devices, parts = self.all_devices, self.parts
        problems = self._name_problems()
        problems += self.wiring.problems(devices=devices, parts=parts).under("wiring")
        problems += self.optics.problems(devices=devices, parts=parts).under("optics")
        return problems

    def illumination_paths(self, source: str, positions: Mapping[str, AxisPosition]) -> list[LightPath]:
        """Every way the light goes from ``source`` to the sample, with each device in ``positions`` at its position
        there. A device that ``positions`` leaves out can be at any position, and holds no part."""
        return self._paths(source, _SAMPLE, positions)

    def detection_paths(self, detector: str, positions: Mapping[str, AxisPosition]) -> list[LightPath]:
        """Every way the light goes from the sample to ``detector``, with each device in ``positions`` at its
        position there. A device that ``positions`` leaves out can be at any position, and holds no part."""
        return self._paths(_SAMPLE, detector, positions)

    def _paths(self, start: str, end: str, positions: Mapping[str, AxisPosition]) -> list[LightPath]:
        """Every way the light goes from ``start`` to ``end``. No way passes a node 2 times."""
        found: list[LightPath] = []
        parts = self.parts

        def walk(name: str, nodes: tuple[str, ...], held: tuple[str, ...]) -> None:
            if name == end:
                found.append(self._path(nodes, held, parts))
                return
            for target, part in self._steps(name, positions, parts):
                if target not in nodes:
                    walk(target, (*nodes, target), held if part is None else (*held, part))

        walk(start, (start,), ())
        return found

    def _steps(
        self, name: str, positions: Mapping[str, AxisPosition], parts: Mapping[str, Part]
    ) -> list[tuple[OpticalNodeName, str | None]]:
        """Each node that ``name`` sends light to, with ``name`` at its position in ``positions``. With it: the part
        that ``name`` holds in the light's way at that position, or ``None``."""
        node = self.optics.root.get(name)
        if not isinstance(node, OpticalElement):
            return []
        given = positions.get(name)
        steps: list[tuple[OpticalNodeName, str | None]] = []
        for label, targets in node.ways().items():
            if label is None or given is None or given == label:
                held = self._part_at(given if label is None else label, parts)
                steps += [(target, held) for target in targets]
        return steps

    def _part_at(self, position: AxisPosition | None, parts: Mapping[str, Part]) -> str | None:
        """The part that a device holds at ``position``: the part of that name, when the part is not a node of the
        optical graph."""
        if isinstance(position, str) and position in parts and position not in self.optics.root:
            return position
        return None

    def _path(self, nodes: tuple[str, ...], held: tuple[str, ...], parts: Mapping[str, Part]) -> LightPath:
        """The path with the magnification and the band of its parts: the nodes that are parts, and the parts in
        ``held``, which the devices on it hold."""
        passed = [parts[name] for name in (*nodes, *held) if name in parts]
        magnifications = [part.magnification for part in passed if isinstance(part, Objective)]
        low: float | None = None
        high: float | None = None
        banded = False
        for part in passed:
            if isinstance(part, Filter):
                banded = True
                low = part.band[0] if low is None else low if part.band[0] is None else max(low, part.band[0])
                high = part.band[1] if high is None else high if part.band[1] is None else min(high, part.band[1])
        return LightPath(nodes, math.prod(magnifications) if magnifications else None, (low, high) if banded else None)

    def _name_problems(self) -> Problems:
        problems = Problems(
            Problem.not_configured("Device", device, code="rig.stage.device_missing", loc=("stage", axis))
            for axis, device in self.stage.devices().items()
            if device not in self.all_devices
        )
        problems += Problems(
            Problem.not_configured("Device", device, code="rig.autosave.device_missing", loc=("autosave", device))
            for device in self.autosave
            if device not in self.all_devices
        )
        if _SAMPLE in self.all_devices or _SAMPLE in self.parts:
            msg = "'sample' names the node where the 2 sides of the optical graph meet, so no device or part takes it."
            problems.add("rig.reserved_name", msg, *self.component_location(_SAMPLE))
        return problems


# === Instrument state ===


class InstrumentState(BaseModel, frozen=True):
    """What the operator edits. ``state.json`` has this form, and so do ``default.yaml`` and a preset. A kind of
    instrument adds its own fields in a subclass. ``metadata`` is the facts about the specimen, in the form that
    ``metadata_cls`` gives."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    metadata_cls: MetadataCls = ExperimentMetadata
    metadata: Annotated[dict[str, Any], NotDefault] = Field(default_factory=dict, validate_default=True)

    @field_validator("metadata")
    @classmethod
    def _check_metadata(cls, metadata: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        form = info.data.get("metadata_cls")  # missing when metadata_cls itself failed
        return metadata if form is None else form.model_validate(metadata).model_dump()

    @classmethod
    def default_fields(cls) -> frozenset[str]:
        """The fields that can be saved as a default: those with no ``NotDefault`` mark."""
        return frozenset(name for name, field in cls.model_fields.items() if NotDefault not in field.metadata)

    @abstractmethod
    def problems(self, config: InstrumentConfig) -> Problems:
        """Return the problems of this state against ``config``."""
