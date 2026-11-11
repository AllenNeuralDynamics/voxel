"""The ``hal`` part of an instrument file: the bench, for every kind of instrument."""

import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Annotated, Any, Literal, NamedTuple, Self

from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    PlainSerializer,
    RootModel,
    Tag,
    field_validator,
    model_validator,
)
from rigup.config import DeviceUid, RigConfig
from vxlib.schema import FrozenModel, UniqueList, check_identifier, identifier
from vxlib.units import Quantity, Time, Voltage, Wavelength
from vxlib.vector import Span, Vec3D

from vxl.models import AxisPosition

from .errors import Violation, ViolationLoc, not_configured, under

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


# === Parts ===

PartName = Annotated[str, identifier("Part name")]
"""A part with no driver, such as a galvo or an objective."""

_Magnification = Annotated[float, Field(gt=0, allow_inf_nan=False)]


def _check_band(band: tuple[Wavelength | None, Wavelength | None]) -> tuple[Wavelength | None, Wavelength | None]:
    low, high = band
    if low is None and high is None:
        raise ValueError("a band needs at least 1 end")
    if low is not None and high is not None and not low < high:
        raise ValueError(f"a band goes from low to high, got [{low}, {high}]")
    return band


_PassBand = Annotated[tuple[Wavelength | None, Wavelength | None], AfterValidator(_check_band)]
"""The wavelengths that a part lets through, from low to high. ``null`` leaves an end open, as a long-pass filter
does."""


class Part(FrozenModel):
    """A thing on the bench with no driver. ``kind`` says what it is, such as a galvo or a tunable lens."""

    kind: Annotated[str, Field(min_length=1)] | None = None
    label: str | None = None


class Filter(Part):
    """A part with ``kind: filter``: it lets 1 band of wavelengths through."""

    band: _PassBand


class Objective(Part):
    """A part with ``kind: objective``: it magnifies. 1 objective can stand for the objective and its tube lens
    together."""

    magnification: _Magnification


def _part_kind(part: object) -> str:
    if isinstance(part, Mapping):
        kind = part.get("kind")
        return kind if kind in ("filter", "objective") else "part"
    return "filter" if isinstance(part, Filter) else "objective" if isinstance(part, Objective) else "part"


type _AnyPart = Annotated[
    Annotated[Filter, Tag("filter")] | Annotated[Objective, Tag("objective")] | Annotated[Part, Tag("part")],
    Discriminator(_part_kind),
]
"""1 part. ``kind`` picks its class: a kind with no class of its own is a plain :class:`Part`."""

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
    """``hal.wiring``: each sending device's wires, by name."""

    model_config = ConfigDict(frozen=True)

    def outputs(self, device: str) -> dict[WireName, DigitalWire | AnalogWire]:
        """Every wire that ``device`` sends, by name."""
        return dict(self.root.get(device, {}))

    def violations(self, *, devices: Collection[str], parts: Collection[str]) -> list[Violation]:
        """Return the problems of the wiring that ``hal`` alone shows."""
        violations: list[Violation] = []
        owner: dict[str, tuple[str, str]] = {}

        def claim(pin: str, sender: str, name: str, pin_loc: ViolationLoc) -> None:
            if pin in owner:
                first_sender, first_name = owner[pin]
                violations.append(
                    Violation(
                        code="hal.wiring.pin_shared",
                        msg=f"Pin '{pin}' is already in wire '{first_sender}.{first_name}'.",
                        loc=pin_loc,
                    )
                )
            else:
                owner[pin] = (sender, name)

        for sender, group in self.root.items():
            if sender not in devices:
                violations.append(not_configured("Device", sender, code="hal.wiring.device_missing", loc=(sender,)))
                continue
            for name, wire in group.items():
                wire_loc = (sender, name)
                claim(f"{sender}/{wire.pin}", sender, name, (*wire_loc, "pin"))
                for index, pin in enumerate(wire.to):
                    if pin.device not in devices and pin.device not in parts:
                        violations.append(
                            Violation(
                                code="hal.wiring.receiver_missing",
                                msg=f"'{pin.device}' is not a device or a part; declare a part in hal.parts.",
                                loc=(*wire_loc, "to", index),
                            )
                        )
                    else:
                        claim(str(pin), sender, name, (*wire_loc, "to", index))
        return violations


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
    """``hal.optics``: each node, by name."""

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

    def violations(
        self,
        *,
        devices: Collection[str],
        parts: Collection[str],
        labels: Mapping[str, Collection[str]],
    ) -> list[Violation]:
        """Return the problems of the optical graph that ``hal`` alone shows."""
        found: list[tuple[str, str, ViolationLoc]] = []
        if _SAMPLE not in self.elements():
            found.append(
                ("sample_missing", "The optical graph needs a 'sample' node with 'to': where the light goes on.", ())
            )
        for name in self.root:
            problems = self._node_problems(name, labels.get(name), parts, is_device=name in devices)
            found += [(code, msg, (name, *at)) for code, msg, at in problems]
        return [Violation(code=f"hal.optics.{code}", msg=msg, loc=at) for code, msg, at in found]

    def _node_problems(
        self, name: str, labels: Collection[str] | None, parts: Collection[str], *, is_device: bool
    ) -> list[tuple[str, str, ViolationLoc]]:
        """The problems of 1 node, as (code, message, location in the node)."""
        node = self.root[name]
        found: list[tuple[str, str, ViolationLoc]] = []
        if name != _SAMPLE and not is_device and name not in parts:
            found.append(("node_unknown", f"'{name}' is not a device or a part; declare it in hal.parts.", ()))
        if isinstance(node, Detector):
            if not is_device:
                found.append(("detector_not_device", f"'{name}' is a detector, and a detector is a device.", ()))
            return found
        found += [
            ("target_missing", f"'{target}' is not a node of hal.optics.", ("to",) if label is None else ("to", label))
            for label, targets in node.ways().items()
            for target in targets
            if target not in self.root
        ]
        if isinstance(node.to, dict) and labels is None:
            found.append(
                (
                    "positions_missing",
                    f"'{name}' gives 'to' for each position, but it is not a device that declares slots.",
                    ("to",),
                )
            )
        elif isinstance(node.to, dict):
            found += [
                ("position_unknown", f"'{label}' is not a position of '{name}' {list(labels or ())}.", ("to", label))
                for label in node.to
                if label not in (labels or ())
            ]
        return found


# === The hal ===


@dataclass(frozen=True)
class LightPath:
    """1 way the light goes from a source, through the sample, to a detector. ``positions`` gives the position of
    each device on it that has positions. ``magnification`` and ``band`` come from the parts that the light passes
    after the sample, in nm for the band, and are ``None`` when no part gives one."""

    nodes: tuple[OpticalNodeName, ...]
    positions: Mapping[OpticalNodeName, str]
    magnification: float | None
    band: tuple[float | None, float | None] | None


class HALConfig(RigConfig, frozen=True):
    """The rig's devices and nodes, plus parts, the stage, wiring and the optical graph."""

    parts: dict[PartName, _AnyPart] = Field(default_factory=dict)
    stage: Stage
    wiring: Wiring = Field(default_factory=lambda: Wiring({}))
    optics: OpticalGraph

    @property
    def _slot_labels(self) -> dict[str, list[str]]:
        """The named positions of each discrete axis, from its ``init.slots``."""
        found: dict[str, list[str]] = {}
        for uid, config in self.device_configs.items():
            slots = config.init.get("slots")
            if isinstance(slots, Mapping):
                found[uid] = [
                    slot if isinstance(slot, str) else slot["label"]
                    for slot in slots.values()
                    if isinstance(slot, str) or (isinstance(slot, Mapping) and isinstance(slot.get("label"), str))
                ]
        return found

    def position_problem(self, device: DeviceUid, value: AxisPosition) -> str | None:
        """Why ``value`` is not a position of ``device``, or ``None`` when it is."""
        labels = self._slot_labels.get(device)
        if labels is not None:
            return None if value in labels else f"'{value}' is not a position of '{device}' {labels}."
        if isinstance(value, str):
            return f"'{device}' declares no slots, so its position is a number in µm, not '{value}'."
        return None

    def light_paths(self, source: str, detector: str) -> list[LightPath]:
        """Every way the light goes from ``source``, through the sample, to ``detector``."""
        holds = self._holds()
        found: list[LightPath] = []

        def walk(
            name: str, nodes: tuple[str, ...], positions: tuple[tuple[str, str], ...], held: tuple[str, ...]
        ) -> None:
            if name == detector:
                if _SAMPLE in nodes:
                    found.append(self._path(nodes, dict(positions), held))
                return
            after_sample = _SAMPLE in nodes
            for target, label, part in self._steps(name, holds):
                if target not in nodes:
                    walk(
                        target,
                        (*nodes, target),
                        positions if label is None else (*positions, (name, label)),
                        (*held, part) if part is not None and after_sample else held,
                    )

        walk(source, (source,), (), ())
        return found

    def selectors(self) -> set[DeviceUid]:
        """The devices of the optical graph whose position changes the light: each sends the light a different way
        at each position, or holds parts."""
        holds = self._holds()
        return {
            name
            for name, node in self.optics.elements().items()
            if name in self.device_uids and (isinstance(node.to, dict) or name in holds)
        }

    def generators(self) -> set[DeviceUid]:
        """The devices that send wires and are not a camera or a stage axis. From the file alone, these are the
        signal generators."""
        others = {*self.optics.detectors(), *self.stage.devices().values()}
        return {sender for sender in self.wiring.root if sender in self.device_uids and sender not in others}

    def violations(self) -> list[Violation]:
        """Return the problems that ``hal`` alone shows."""
        devices, parts = self.device_uids, self.parts
        return [
            *self._name_violations(),
            *self._slot_violations(),
            *under(("wiring",), self.wiring.violations(devices=devices, parts=parts)),
            *under(("optics",), self.optics.violations(devices=devices, parts=parts, labels=self._slot_labels)),
            *self._magnification_violations(),
        ]

    def _holds(self) -> dict[DeviceUid, dict[str, PartName | None]]:
        """Each device of the optical graph that holds parts, with the part at each of its positions, or ``None``
        for a position with no part. A device holds a part when 1 of its slot labels is the name of that part."""
        found: dict[DeviceUid, dict[str, PartName | None]] = {}
        for name in self.optics.elements():
            slots = {
                label: label if label in self.parts and label not in self.optics.root else None
                for label in self._slot_labels.get(name, ())
            }
            if any(part is not None for part in slots.values()):
                found[name] = slots
        return found

    def _steps(
        self, name: str, holds: Mapping[str, Mapping[str, PartName | None]]
    ) -> list[tuple[OpticalNodeName, str | None, PartName | None]]:
        """Each node that ``name`` sends light to. With it: the position that ``name`` needs for that, and the part
        that ``name`` holds in the light's way at that position. Each is ``None`` when there is none."""
        node = self.optics.root.get(name)
        if not isinstance(node, OpticalElement):
            return []
        held = holds.get(name, {})
        steps: list[tuple[OpticalNodeName, str | None, PartName | None]] = []
        for label, targets in node.ways().items():
            if label is not None:
                steps += [(target, label, held.get(label)) for target in targets]
            elif held:
                steps += [(target, slot, part) for slot, part in held.items() for target in targets]
            else:
                steps += [(target, None, None) for target in targets]
        return steps

    def _path(self, nodes: tuple[str, ...], positions: dict[str, str], held: tuple[str, ...]) -> LightPath:
        """The path with the magnification and the band of the parts after the sample: the nodes that are parts,
        and the parts that the devices there hold."""
        passed = [self.parts[name] for name in (*nodes[nodes.index(_SAMPLE) :], *held) if name in self.parts]
        magnifications = [part.magnification for part in passed if isinstance(part, Objective)]
        low: float | None = None
        high: float | None = None
        banded = False
        for part in passed:
            if isinstance(part, Filter):
                banded = True
                low = part.band[0] if low is None else low if part.band[0] is None else max(low, part.band[0])
                high = part.band[1] if high is None else high if part.band[1] is None else min(high, part.band[1])
        return LightPath(
            nodes, positions, math.prod(magnifications) if magnifications else None, (low, high) if banded else None
        )

    def _magnification_violations(self) -> list[Violation]:
        """Each path to a detector needs a part that gives a magnification."""
        sources = self.optics.sources()
        return [
            Violation(
                code="hal.optics.magnification_missing",
                msg=f"A path to '{detector}' has no part that gives a magnification.",
                loc=("optics", detector),
            )
            for detector in self.optics.detectors()
            if any(path.magnification is None for source in sources for path in self.light_paths(source, detector))
        ]

    def _slot_violations(self) -> list[Violation]:
        """A slot label can be the name of a part, so it has the form of a name."""
        violations: list[Violation] = []
        for device, labels in self._slot_labels.items():
            for label in labels:
                try:
                    check_identifier(label, "Slot label")
                except ValueError as error:
                    loc = ("devices", device, "init", "slots")
                    violations.append(Violation(code="hal.devices.slot_label", msg=str(error), loc=loc))
        return violations

    def _name_violations(self) -> list[Violation]:
        violations = [
            not_configured("Device", device, code="hal.stage.device_missing", loc=("stage", axis))
            for axis, device in self.stage.devices().items()
            if device not in self.device_uids
        ]
        if _SAMPLE in self.parts or _SAMPLE in self.device_uids:
            violations.append(
                Violation(
                    code="hal.reserved_name",
                    msg="'sample' names the node where the 2 sides of the optical graph meet, so no device or part "
                    "takes it.",
                    loc=("parts" if _SAMPLE in self.parts else "devices", _SAMPLE),
                )
            )
        violations += [
            Violation(
                code="hal.parts.device_name",
                msg=f"'{part}' is a device, so it is not also a part.",
                loc=("parts", part),
            )
            for part in self.parts
            if part in self.device_uids
        ]
        used = {pin.device for group in self.wiring.root.values() for wire in group.values() for pin in wire.to}
        used.update(self.optics.root)
        used.update(part for slots in self._holds().values() for part in slots.values() if part is not None)
        violations += [
            Violation(
                code="hal.parts.unused",
                msg=f"Part '{part}' is not used by any wire or optical node.",
                loc=("parts", part),
            )
            for part in self.parts
            if part not in used
        ]
        return violations


__all__ = [
    "AnalogWire",
    "Detector",
    "DigitalWire",
    "Filter",
    "HALConfig",
    "LightPath",
    "Objective",
    "OpticalElement",
    "OpticalGraph",
    "OpticalNode",
    "OpticalNodeName",
    "Part",
    "PartName",
    "Pin",
    "SpecimenAxis",
    "Stage",
    "Wire",
    "WireConfig",
    "WireName",
    "Wiring",
]
