"""``hal.light``: the light graph, from the light sources through the sample to the detectors, and the rules that set
its nodes."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from math import prod
from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, ConfigDict, Discriminator, Field, RootModel, Tag, model_validator
from vxlib.schema import FrozenModel, repeated

from vxl.config.basics import Direction, NodeName, SpecimenAxis, Violation, ViolationLoc, check_right_angle

SAMPLE = "sample"
"""The node where the light meets the sample."""

PositionLabel = Annotated[str, Field(min_length=1)]
"""1 of the labels in a discrete axis's ``init.slots``, such as a filter."""

PositionValue = Annotated[float, Field(allow_inf_nan=False)] | PositionLabel
"""A label when the axis declares ``slots``, otherwise a number in µm."""

Magnification = Annotated[float, Field(gt=0, allow_inf_nan=False)]


def _unique_targets(value: list[str]) -> list[str]:
    if duplicates := repeated(value):
        raise ValueError(f"parts in 'to' must be unique (repeated: {duplicates})")
    return value


Targets = Annotated[list[NodeName], Field(min_length=2), AfterValidator(_unique_targets)]
"""Several parts that get the light at once."""


class Split(FrozenModel):
    """How a selector can follow the stage: on ``axis``, it takes ``lower`` below a point and ``upper`` above it."""

    axis: SpecimenAxis
    lower: PositionLabel
    upper: PositionLabel

    @model_validator(mode="after")
    def _two_sides(self) -> Self:
        if self.lower == self.upper:
            raise ValueError("'lower' and 'upper' must be different positions")
        return self


class SetByInstrument(FrozenModel):
    """``set_by: instrument`` for a selector that can follow the stage, as ``split`` says."""

    kind: Literal["instrument"]
    split: Split


type SetBy = Literal["channel", "profile", "instrument"] | SetByInstrument
"""Who holds a node's position: each channel, each profile, or the instrument, in ``selections``."""

type StageSide = Literal["lower", "upper"]


class FixedSelection(FrozenModel):
    """The instrument keeps the selector at 1 position."""

    kind: Literal["fixed"]
    position: PositionValue


class SplitSelection(FrozenModel):
    """The selector follows the stage, as its ``split`` says. ``at`` is the point, in µm, where it changes position;
    within ``margin`` of the point, it keeps its last position."""

    kind: Literal["split"]
    at: float = Field(allow_inf_nan=False)
    margin: float = Field(default=0, ge=0, allow_inf_nan=False)

    def side(self, coordinate: float, *, previous: StageSide | None = None) -> StageSide:
        """The side of the point that ``coordinate`` is on. Within the margin, it stays on ``previous``."""
        if previous == "lower":
            return "upper" if coordinate >= self.at + self.margin else "lower"
        if previous == "upper":
            return "lower" if coordinate < self.at - self.margin else "upper"
        return "lower" if coordinate < self.at else "upper"


type Selection = Annotated[FixedSelection | SplitSelection, Field(discriminator="kind")]
"""How the instrument sets 1 ``set_by: instrument`` node."""


class Combiner(FrozenModel):
    """A part where beams join."""

    kind: Literal["combiner"]
    to: NodeName


class Splitter(FrozenModel):
    """A passive part that sends the light to several parts at once."""

    kind: Literal["splitter"]
    to: Targets


class Element(FrozenModel):
    """A device or a part that passes the light on. ``magnification`` counts only after the sample."""

    to: NodeName
    set_by: SetBy | None = None
    magnification: Magnification | None = None


class PathSelector(FrozenModel):
    """A device that sends the light to 1 node, or several, for each position."""

    to: dict[PositionLabel, NodeName | Targets]
    set_by: SetBy


class Detector(FrozenModel):
    """A detector, where the light ends. ``width`` and ``height`` are the directions of the frame's sides; a line camera
    has only ``width``. The magnification comes from the elements before it, such as the objective."""

    width: Direction
    height: Direction | None = None

    @model_validator(mode="after")
    def _right_angle(self) -> Self:
        if self.height is not None:
            check_right_angle(self.width, self.height)
        return self


def _tag(value: Any) -> str:
    kind = value.get("kind") if isinstance(value, Mapping) else getattr(value, "kind", None)
    if kind is not None:
        return str(kind)
    to = value.get("to") if isinstance(value, Mapping) else getattr(value, "to", None)
    if to is None:
        return "detector"
    return "path_selector" if isinstance(to, Mapping) else "element"


type LightNode = Annotated[
    Annotated[Combiner, Tag("combiner")]
    | Annotated[Splitter, Tag("splitter")]
    | Annotated[PathSelector, Tag("path_selector")]
    | Annotated[Element, Tag("element")]
    | Annotated[Detector, Tag("detector")],
    Discriminator(
        _tag,
        custom_error_type="light_node_kind",
        custom_error_message="a node's kind is combiner or splitter, and only a part has one",
    ),
]
"""1 node, told apart by ``kind`` or the shape of ``to``. A detector has no ``to``."""


def targets(entry: object) -> list[str]:
    """Every node that ``entry`` sends light to."""
    return [target for target, _ in _steps(entry)]


def _steps(entry: object) -> list[tuple[str, str | None]]:
    """Each node that ``entry`` sends light to, with the position of the path selector that it needs, or ``None``."""
    to = getattr(entry, "to", None)
    if isinstance(to, str):
        return [(to, None)]
    if isinstance(to, list):
        return [(target, None) for target in to]
    if isinstance(to, dict):
        return [
            (target, position)
            for position, sent in to.items()
            for target in ([sent] if isinstance(sent, str) else sent)
        ]
    return []


@dataclass(frozen=True)
class LightPath:
    """1 way the light goes from a source, through the sample, to a detector. ``positions`` gives each path selector's
    position; ``magnification`` is ``None`` when no node after the sample gives one."""

    nodes: tuple[NodeName, ...]
    positions: Mapping[NodeName, str]
    magnification: float | None


class LightGraph(RootModel[dict[NodeName, LightNode]]):
    """``hal.light``: each node, by name."""

    model_config = ConfigDict(frozen=True)

    def sources(self) -> dict[NodeName, Element | PathSelector | Combiner | Splitter]:
        """The nodes that nothing sends light to."""
        lit = {target for entry in self.root.values() for target in targets(entry)}
        return {
            name: entry
            for name, entry in self.root.items()
            if name not in lit and name != SAMPLE and not isinstance(entry, Detector)
        }

    def detectors(self) -> dict[NodeName, Detector]:
        """The nodes with no ``to``."""
        return {name: entry for name, entry in self.root.items() if isinstance(entry, Detector)}

    def rules(self) -> dict[NodeName, SetBy]:
        """Each node that a rule sets, with its rule."""
        return {
            name: entry.set_by
            for name, entry in self.root.items()
            if isinstance(entry, Element | PathSelector) and entry.set_by is not None
        }

    def paths(self, source: str, detector: str) -> list[LightPath]:
        """Every way the light goes from ``source``, through the sample, to ``detector``."""
        found: list[LightPath] = []

        def walk(node: str, nodes: tuple[str, ...], positions: tuple[tuple[str, str], ...]) -> None:
            if node == detector:
                if SAMPLE in nodes:
                    after = nodes[nodes.index(SAMPLE) :]
                    values = [m for name in after if (m := getattr(self.root.get(name), "magnification", None))]
                    found.append(LightPath(nodes, dict(positions), prod(values) if values else None))
                return
            for target, position in _steps(self.root.get(node)):
                if target not in nodes:
                    walk(target, (*nodes, target), positions if position is None else (*positions, (node, position)))

        walk(source, (source,), ())
        return found

    def violations(
        self,
        *,
        devices: Collection[str],
        parts: Collection[str],
        labels: Mapping[str, Collection[str]],
    ) -> list[Violation]:
        """Return the problems of the light graph that ``hal`` alone shows."""
        nodes = self.root
        found: list[tuple[str, str, ViolationLoc]] = []
        if not isinstance(nodes.get(SAMPLE), Element):
            found.append(
                ("sample_missing", "The light graph needs a 'sample' node with 'to': where the light goes on.", ())
            )
        for name, entry in nodes.items():
            problems = _node_problems(
                name, entry, nodes, labels.get(name), is_device=name in devices, is_part=name in parts
            )
            found += [(code, msg, (name, *at)) for code, msg, at in problems]

        after, pending = {SAMPLE}, [SAMPLE]
        while pending:
            for target in targets(nodes.get(pending.pop())):
                if target not in after:
                    after.add(target)
                    pending.append(target)
        found += [
            ("magnification_before_sample", f"'{name}' is before the sample, so it gives no magnification.", (name,))
            for name, entry in nodes.items()
            if getattr(entry, "magnification", None) is not None and name not in after
        ]
        sources = self.sources()
        for detector in self.detectors():
            if any(path.magnification is None for source in sources for path in self.paths(source, detector)):
                found.append(
                    ("magnification_missing", f"No node on a path to '{detector}' gives a magnification.", (detector,))
                )
        return [Violation(code=f"hal.light.{code}", msg=msg, loc=at) for code, msg, at in found]


def _node_problems(
    name: str,
    entry: object,
    nodes: Collection[str],
    labels: Collection[str] | None,
    *,
    is_device: bool,
    is_part: bool,
) -> list[tuple[str, str, ViolationLoc]]:
    """The problems of 1 node, as (code, message, location in the node)."""
    found: list[tuple[str, str, ViolationLoc]] = []
    if name != SAMPLE and not is_device and not is_part:
        found.append(("node_unknown", f"'{name}' is not a device or a part; declare it in hal.parts.", ()))
    if isinstance(entry, Combiner | Splitter) and is_device:
        found.append(("kind_on_device", f"'{name}' is a device, so its driver says what it is.", ("kind",)))
    if isinstance(entry, Detector) and not is_device:
        found.append(
            ("detector_not_device", f"'{name}' has no 'to', so it is a detector, and a detector is a device.", ())
        )
    found += [
        ("target_missing", f"'{t}' is not a node of hal.light.", ("to",)) for t in targets(entry) if t not in nodes
    ]
    if not isinstance(entry, Element | PathSelector):
        return found

    named: list[tuple[str, ViolationLoc]] = []
    if isinstance(entry, PathSelector):
        if labels is None:
            found.append(("positions_missing", f"'{name}' sends the light by position, but declares no slots.", ()))
        named += [(position, ("to", position)) for position in entry.to]
    rule = entry.set_by
    if rule is not None and not is_device:
        found.append(("set_by_not_device", f"Only a device's position can be set; '{name}' is not one.", ("set_by",)))
    elif isinstance(rule, SetByInstrument):
        if labels is None:
            found.append(
                ("set_by_needs_slots", f"A split picks a label, so '{name}' needs slots.", ("set_by", "split"))
            )
        named += [(rule.split.lower, ("set_by", "split", "lower")), (rule.split.upper, ("set_by", "split", "upper"))]
    if labels is not None:
        found += [
            ("position_unknown", f"'{position}' is not a position of '{name}' {list(labels)}.", at)
            for position, at in named
            if position not in labels
        ]
    return found


__all__ = [
    "SAMPLE",
    "Combiner",
    "Detector",
    "Element",
    "FixedSelection",
    "LightGraph",
    "LightNode",
    "LightPath",
    "Magnification",
    "PathSelector",
    "PositionLabel",
    "PositionValue",
    "Selection",
    "SetBy",
    "SetByInstrument",
    "Split",
    "SplitSelection",
    "Splitter",
    "StageSide",
    "targets",
]
