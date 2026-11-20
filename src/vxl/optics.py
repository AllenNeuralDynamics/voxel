"""The optical graph of a rig: where light goes from each source to the specimen and on to each detector."""

import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from functools import cached_property
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Discriminator, Field, RootModel, Tag, field_validator, model_validator
from vxlib.issues import Problems
from vxlib.schema import FrozenModel, UniqueList, identifier
from vxlib.vector import Vec3D

from rigup import Part
from vxl.parts import Filter, Objective

type SpecimenAxis = Literal["x", "y", "z"]


type _SpecimenDirection = dict[SpecimenAxis, float]
"""A direction in specimen axes, such as ``{x: 1, z: 1}``; its length is ignored."""

type AxisPosition = Annotated[float, Field(allow_inf_nan=False)] | str
"""An axis position: a number, or a position name."""

OpticalNodeName = Annotated[str, identifier("Optical node")]
"""A device, a part, or ``specimen``."""

SPECIMEN = "specimen"
"""The node where the light meets the specimen."""


_NodeList = Annotated[UniqueList[OpticalNodeName], Field(min_length=2)]
"""Nodes that get the light at once."""


class Detector(FrozenModel):
    """A node where light ends: a camera. ``width`` and ``height`` are the frame's side directions, at 90°."""

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
        """Unit vectors along the frame's width and height."""

        def unit(direction: _SpecimenDirection) -> Vec3D:
            vector = Vec3D(x=direction.get("x", 0.0), y=direction.get("y", 0.0), z=direction.get("z", 0.0))
            return vector / math.hypot(*vector)

        return unit(self.width), unit(self.height)


class OpticalElement(FrozenModel):
    """A node that passes light on. ``to`` is the next node, several at once, or a node per position; light stops at a
    position left out."""

    to: OpticalNodeName | _NodeList | Annotated[dict[str, OpticalNodeName | _NodeList], Field(min_length=1)]

    def ways(self) -> dict[str | None, list[OpticalNodeName]]:
        """The next nodes for each position; the key is ``None`` when position does not matter."""
        ways = self.to.items() if isinstance(self.to, dict) else [(None, self.to)]
        return {label: [way] if isinstance(way, str) else list(way) for label, way in ways}


def _node_kind(node: object) -> str:
    if isinstance(node, Mapping):
        return "detector" if "width" in node or "height" in node else "element"
    return "detector" if isinstance(node, Detector) else "element"


type OpticalNode = Annotated[
    Annotated[Detector, Tag("detector")] | Annotated[OpticalElement, Tag("element")], Discriminator(_node_kind)
]
"""A node; one with ``width`` or ``height`` is a detector."""


@dataclass(frozen=True)
class LightPath:
    """A way from a source to the specimen, or from the specimen to a detector, with the position each router on it
    needs."""

    nodes: tuple[OpticalNodeName, ...]
    positions: Mapping[OpticalNodeName, str]

    def fits(self, positions: Mapping[str, AxisPosition | None]) -> bool:
        """Whether light takes this way at ``positions``. A device left out may be anywhere; one at ``None`` fits no
        way that needs it."""
        return all(positions.get(device, label) == label for device, label in self.positions.items())


class OpticalGraph(RootModel[dict[OpticalNodeName, OpticalNode]]):
    """``optics``: each node by name."""

    model_config = ConfigDict(frozen=True)

    def elements(self) -> dict[OpticalNodeName, OpticalElement]:
        """The nodes that pass light on."""
        return {name: node for name, node in self.root.items() if isinstance(node, OpticalElement)}

    def detectors(self) -> dict[OpticalNodeName, Detector]:
        """The nodes where light ends."""
        return {name: node for name, node in self.root.items() if isinstance(node, Detector)}

    def sources(self) -> dict[OpticalNodeName, OpticalElement]:
        """The nodes that receive no light."""
        elements = self.elements()
        lit = {target for node in elements.values() for targets in node.ways().values() for target in targets}
        return {name: node for name, node in elements.items() if name not in lit and name != SPECIMEN}

    def routers(self) -> dict[OpticalNodeName, tuple[str, ...]]:
        """The nodes that route light by position, with their positions."""
        return {name: tuple(node.to) for name, node in self.elements().items() if isinstance(node.to, dict)}

    def paths_from(self, source: str, positions: Mapping[str, AxisPosition | None]) -> list[LightPath]:
        """The ways from ``source`` to the specimen at ``positions``."""
        return [path for path in self._paths if path.nodes[0] == source and path.fits(positions)]

    def paths_to(self, detector: str, positions: Mapping[str, AxisPosition | None]) -> list[LightPath]:
        """The ways from the specimen to ``detector`` at ``positions``."""
        return [path for path in self._paths if path.nodes[-1] == detector and path.fits(positions)]

    def magnification(
        self, path: LightPath, positions: Mapping[str, AxisPosition | None], parts: Mapping[str, Part]
    ) -> float | None:
        """The product of the objectives' magnifications on ``path``; ``None`` without an objective."""
        found = [part.magnification for part in self.parts_on(path, positions, parts) if isinstance(part, Objective)]
        return math.prod(found) if found else None

    def band(
        self, path: LightPath, positions: Mapping[str, AxisPosition | None], parts: Mapping[str, Part]
    ) -> tuple[float | None, float | None] | None:
        """The wavelengths in nm that the filters on ``path`` let through; ``None`` without a filter."""
        low: float | None = None
        high: float | None = None
        banded = False
        for part in self.parts_on(path, positions, parts):
            if isinstance(part, Filter):
                banded = True
                low = part.band[0] if low is None else low if part.band[0] is None else max(low, part.band[0])
                high = part.band[1] if high is None else high if part.band[1] is None else min(high, part.band[1])
        return (low, high) if banded else None

    def camera_axes(
        self, camera: str, positions: Mapping[str, AxisPosition | None], parts: Mapping[str, Part]
    ) -> tuple[Vec3D, Vec3D]:
        """Where 1 µm along ``camera``'s width and height lands in the specimen. Raise ``ValueError`` when no path
        reaches it or its paths disagree on magnification."""
        paths = self.paths_to(camera, positions)
        if not paths:
            raise ValueError(f"No light goes from the specimen to '{camera}' with {dict(positions)}.")
        found = {self.magnification(path, positions, parts) for path in paths}
        if len(found) != 1 or (magnification := found.pop()) is None:
            raise ValueError(f"The light paths from the specimen to '{camera}' do not give 1 magnification.")
        width, height = self.detectors()[camera].sides()
        return width / magnification, height / magnification

    def parts_on(
        self, path: LightPath, positions: Mapping[str, AxisPosition | None], parts: Mapping[str, Part]
    ) -> list[Part]:
        """The parts on ``path``: its part nodes, and the part each device on it holds, named by its position."""
        at = (path.positions.get(node, positions.get(node)) for node in path.nodes[:-1])
        held = (position for position in at if isinstance(position, str) and position not in self.root)
        return [parts[name] for name in (*path.nodes, *held) if name in parts]

    @cached_property
    def _paths(self) -> tuple[LightPath, ...]:
        """Every way to and from the specimen, visiting no node twice."""
        found: list[LightPath] = []
        elements = self.elements()

        def walk(end: str, nodes: tuple[str, ...], positions: dict[str, str]) -> None:
            here = nodes[-1]
            if here == end:
                found.append(LightPath(nodes, MappingProxyType(positions)))
            elif here in elements:
                for label, targets in elements[here].ways().items():
                    needs = positions if label is None else {**positions, here: label}
                    for target in targets:
                        if target not in nodes:
                            walk(end, (*nodes, target), needs)

        for source in self.sources():
            walk(SPECIMEN, (source,), {})
        for detector in self.detectors():
            walk(detector, (SPECIMEN,), {})
        return tuple(found)

    def problems(self, *, devices: Collection[str], parts: Collection[str]) -> Problems:
        """The problems that need no hardware: no ``specimen``, unknown nodes, detectors that are not devices, and
        ``to`` targets that are not nodes."""
        problems = Problems()
        if SPECIMEN not in self.elements():
            msg = "The optical graph needs a 'specimen' node with 'to': where the light goes on."
            problems.add("rig.optics.specimen_missing", msg)
        for name, node in self.root.items():
            is_device = name in devices
            if name != SPECIMEN and not is_device and name not in parts:
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
