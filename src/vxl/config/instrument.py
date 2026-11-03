"""The whole instrument file: ``hal`` plus the defaults that seed each instrument's state."""

import datetime
import secrets
from collections.abc import Mapping
from typing import Annotated, Any, Self

from ome_zarr_writer import WriterSettings
from pydantic import Field, field_validator
from vxlib.schema import FrozenModel, repeated

from .hal import HALConfig, SelectRoutingDefinition, SplitRoutingDefinition
from .identifiers import RouteName, RoutingDimension
from .imaging import ImagingConfig
from .metadata import ExperimentMetadata, MetadataCls
from .tasks import Task, TaskSettings
from .violations import Violation, ViolationLoc, assignment_violations, not_configured


class SelectRoutingRule(FrozenModel):
    selected: RouteName


class SplitRoutingRule(FrozenModel):
    threshold: float = Field(allow_inf_nan=False)

    def resolve(self, coordinate: float, *, previous: str | None = None, margin: float = 0) -> str:
        """Resolve 1 side, keeping ``previous`` within the symmetric hysteresis margin."""
        if margin < 0:
            raise ValueError("margin must be non-negative")
        if previous == "lower":
            return "upper" if coordinate >= self.threshold + margin else "lower"
        if previous == "upper":
            return "lower" if coordinate < self.threshold - margin else "upper"
        return "lower" if coordinate < self.threshold else "upper"


type RoutingRule = SelectRoutingRule | SplitRoutingRule


class InstrumentDefaults(FrozenModel):
    """Everything that can live in ``config.default``."""

    imaging: ImagingConfig
    task: TaskSettings
    """The settings a new task takes when it leaves them out."""
    routing: dict[RoutingDimension, RoutingRule] = Field(default_factory=dict)
    metadata_cls: MetadataCls = ExperimentMetadata
    output: WriterSettings = Field(default_factory=WriterSettings)

    def resolve_routes(
        self,
        hal: HALConfig,
        *,
        x: float,
        y: float,
        previous: Mapping[str, str] | None = None,
        margins: Mapping[str, float] | None = None,
    ) -> dict[RoutingDimension, RouteName]:
        """Resolve each routing dimension from its rule and an XY position."""
        coordinates = {"x": x, "y": y}
        previous = previous or {}
        margins = margins or {}
        routes = {}
        for dimension, rule in self.routing.items():
            definition = hal.optical_routing.root[dimension]
            match definition, rule:
                case SelectRoutingDefinition(), SelectRoutingRule(selected=route):
                    routes[dimension] = route
                case SplitRoutingDefinition(), SplitRoutingRule():
                    routes[dimension] = rule.resolve(
                        coordinates[definition.axis],
                        previous=previous.get(dimension),
                        margin=margins.get(definition.axis, 0),
                    )
                case _:
                    raise ValueError(f"Routing settings do not match dimension '{dimension}'")
        return routes

    def semantic_violations(self, hal: HALConfig, *, loc: ViolationLoc) -> list[Violation]:
        imaging_loc = (*loc, "imaging")
        return [
            *self.imaging.logical_violations(loc=imaging_loc),
            *self.imaging.hal_violations(hal, loc=imaging_loc),
            *self.task.capture_violations(hal.capture_settings, loc=(*loc, "task")),
            *self._routing_violations(hal, loc=(*loc, "routing")),
        ]

    def _routing_violations(self, hal: HALConfig, *, loc: ViolationLoc) -> list[Violation]:
        participating = {
            dimension
            for paths in (hal.detection, hal.illumination)
            for path in paths.values()
            for dimension in path.routing
            if dimension in hal.optical_routing.root
        }
        violations = assignment_violations(
            expected=participating,
            assigned=self.routing,
            loc=loc,
            code="optical_routing.rule",
            label="routing rule",
        )
        for dimension, rule in self.routing.items():
            definition = hal.optical_routing.root.get(dimension)
            if definition is None or dimension not in participating:
                continue
            if isinstance(definition, SelectRoutingDefinition) != isinstance(rule, SelectRoutingRule):
                violations.append(
                    Violation(
                        code="optical_routing.rule.type_mismatch",
                        msg=f"Routing settings must match configured type '{definition.type}'.",
                        loc=(*loc, dimension),
                    )
                )
            elif isinstance(rule, SelectRoutingRule) and rule.selected not in definition.routes:
                violations.append(
                    Violation(
                        code="optical_routing.rule.route_missing",
                        msg=f"Route '{rule.selected}' is not defined for routing dimension '{dimension}'.",
                        loc=(*loc, dimension, "selected"),
                    )
                )
        return violations


class InstrumentPreset(InstrumentDefaults):
    """Reusable instrument settings and tasks, without specimen metadata."""

    plan: list[Task] = Field(default_factory=list)

    @field_validator("plan")
    @classmethod
    def _unique_task_ids(cls, plan: list[Task]) -> list[Task]:
        if duplicates := repeated(task.id for task in plan):
            raise ValueError(f"task ids must be unique (repeated: {duplicates})")
        return plan

    @classmethod
    def from_state(cls, state: "InstrumentState") -> Self:
        """The reusable preset fields of a complete instrument state."""
        return cls.model_validate(state.model_dump(include=set(cls.model_fields)))

    def semantic_violations(self, hal: HALConfig, *, loc: ViolationLoc) -> list[Violation]:
        violations = super().semantic_violations(hal, loc=loc)
        for index, task in enumerate(self.plan):
            task_loc = (*loc, "plan", index)
            violations += task.capture_violations(hal.capture_settings, loc=task_loc)
            for profile_index, profile_id in enumerate(task.profiles):
                if profile_id not in self.imaging.profiles:
                    violations.append(
                        not_configured(
                            "Profile",
                            profile_id,
                            code="task.profile_missing",
                            loc=(*task_loc, "profiles", profile_index),
                        )
                    )
        return violations


class InstrumentState(InstrumentPreset):
    """Saved state that the operator edits: a preset plus specimen metadata and the time it last changed."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    last_modified: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.UTC))


_ID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
"""Crockford's base32 in lowercase: digits and letters without i, l, o and u, which are easy to misread."""

InstrumentId = Annotated[str, Field(pattern=f"^[0-7][{_ID_ALPHABET}]{{25}}$")]
"""128 random bits in 26 characters: as unique as a UUID, and safe in URLs and file names."""

InstrumentName = Annotated[str, Field(min_length=1, max_length=32)]
"""A label for people. Records and the Lab use the ID."""

InstrumentModel = Annotated[str, Field(min_length=1, max_length=64)]
"""The lab's own label for the kind of instrument, such as ``exaSPIM`` or ``exaspim.v2``."""


def new_instrument_id() -> str:
    """Return a new random :data:`InstrumentId`."""
    value = secrets.randbits(128)
    return "".join(_ID_ALPHABET[(value >> shift) & 31] for shift in range(125, -1, -5))


def _file_violations(hal: HALConfig, default: InstrumentDefaults) -> list[Violation]:
    return [
        *hal.semantic_violations(loc=("config", "hal")),
        *default.semantic_violations(hal, loc=("config", "default")),
    ]


class InstrumentTemplate(FrozenModel):
    """A shipped instrument design: an instrument file without an ID or a name."""

    model: InstrumentModel | None = None
    hal: HALConfig
    default: InstrumentDefaults

    def instantiate(self, name: str) -> "InstrumentConfig":
        """Make a new instrument from this design, with a new ID."""
        return InstrumentConfig.model_validate({"id": new_instrument_id(), "name": name, **dict(self)})

    def semantic_violations(self) -> list[Violation]:
        """Return every relationship that the file alone shows cannot resolve."""
        return _file_violations(self.hal, self.default)


class InstrumentConfig(FrozenModel):
    """An instrument's ``config.yaml``. Its ID is made when the instrument is created and never changes."""

    id: InstrumentId
    name: InstrumentName
    model: InstrumentModel | None = None
    hal: HALConfig
    default: InstrumentDefaults

    def semantic_violations(self) -> list[Violation]:
        """Return every relationship that the file alone shows cannot resolve."""
        return _file_violations(self.hal, self.default)


__all__ = [
    "InstrumentConfig",
    "InstrumentDefaults",
    "InstrumentId",
    "InstrumentModel",
    "InstrumentName",
    "InstrumentPreset",
    "InstrumentState",
    "InstrumentTemplate",
    "RoutingRule",
    "SelectRoutingRule",
    "SplitRoutingRule",
    "new_instrument_id",
]
