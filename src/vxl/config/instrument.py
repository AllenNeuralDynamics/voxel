"""The instrument files: ``config.yaml``, its defaults, ``state.json`` and presets."""

import datetime
import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Self

from ome_zarr_writer import WriterSettings
from pydantic import Field, field_validator
from rigup.config import DeviceUid
from ruamel.yaml import YAML
from vxlib.schema import FrozenModel, repeated

from .basics import NodeName, Violation, assignment_violations, not_configured, under
from .engine import EngineConfig
from .hal import HALConfig
from .imaging import ImagingConfig, PropertyName
from .light import FixedSelection, Selection, SetBy, SetByInstrument
from .metadata import ExperimentMetadata, MetadataCls
from .tasks import Task, TaskSettings

if TYPE_CHECKING:
    from vxl.instrument_next.engine import Engine

_ID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
"""Crockford's base32 in lowercase: digits and letters without i, l, o and u, which are easy to misread."""

InstrumentId = Annotated[str, Field(pattern=f"^[0-7][{_ID_ALPHABET}]{{25}}$")]
"""128 random bits in 26 characters, safe in URLs and file names."""

InstrumentName = Annotated[str, Field(min_length=1, max_length=32)]
"""A label for people."""

InstrumentModel = Annotated[str, Field(min_length=1, max_length=64)]
"""The lab's own label for the kind of instrument, such as ``exaSPIM`` or ``exaspim.v2``."""


def held_by_instrument(hal: HALConfig) -> dict[NodeName, SetBy]:
    """Each node of ``hal.light`` whose position the instrument holds in ``selections``, with its rule."""
    return {
        node: rule
        for node, rule in hal.light.rules().items()
        if rule == "instrument" or isinstance(rule, SetByInstrument)
    }


class InstrumentDefaults(FrozenModel):
    """``config.default``: what seeds each instrument's state. ``props`` holds the device properties that every profile
    starts from, and a profile's ``props`` override them. ``selections`` holds how the instrument sets each
    ``set_by: instrument`` node."""

    imaging: ImagingConfig
    task: TaskSettings
    props: dict[DeviceUid, dict[PropertyName, Any]] = Field(default_factory=dict)
    selections: dict[NodeName, Selection] = Field(default_factory=dict)
    metadata_cls: MetadataCls = ExperimentMetadata
    output: WriterSettings = Field(default_factory=WriterSettings)

    def violations(self, hal: HALConfig, engine: "Engine[Any]") -> list[Violation]:
        """Return the problems of these settings against ``hal`` and ``engine``."""
        return [
            *under(("imaging",), self.imaging.violations(hal, engine)),
            *under(("task",), self.task.violations(engine)),
            *under(("props",), self._props_violations(hal, engine)),
            *under(("selections",), self._selection_violations(hal)),
        ]

    def _props_violations(self, hal: HALConfig, engine: "Engine[Any]") -> list[Violation]:
        owned = engine.owned_devices()
        violations: list[Violation] = []
        for device in self.props:
            if device not in hal.device_uids:
                violations.append(not_configured("Device", device, code="props.device_missing", loc=(device,)))
            elif device in owned:
                violations.append(
                    Violation(
                        code="props.engine_owned",
                        msg=f"The engine names '{device}', so it sets it.",
                        loc=(device,),
                    )
                )
        return violations

    def _selection_violations(self, hal: HALConfig) -> list[Violation]:
        """1 entry for each node that the instrument holds, a position that the node has, and a split only where the
        node's rule has one."""
        held = held_by_instrument(hal)
        violations = assignment_violations(
            expected=held, assigned=self.selections, loc=(), code="selections", label="selection"
        )
        for node, selection in self.selections.items():
            if (rule := held.get(node)) is None:
                continue
            if isinstance(selection, FixedSelection):
                if (problem := hal.position_problem(node, selection.position)) is not None:
                    violations.append(
                        Violation(code="selections.position_invalid", msg=problem, loc=(node, "position"))
                    )
            elif not isinstance(rule, SetByInstrument):
                violations.append(
                    Violation(
                        code="selections.split_unknown",
                        msg=f"'{node}' has no split in hal.light, so its selection must be fixed.",
                        loc=(node, "kind"),
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
        return cls.model_validate({name: getattr(state, name) for name in cls.model_fields})

    def violations(self, hal: HALConfig, engine: "Engine[Any]") -> list[Violation]:
        violations = super().violations(hal, engine)
        for index, task in enumerate(self.plan):
            found = task.violations(engine)
            found += [
                not_configured("Profile", profile_id, code="task.profile_missing", loc=("profiles", profile_index))
                for profile_index, profile_id in enumerate(task.profiles)
                if profile_id not in self.imaging.profiles
            ]
            violations += under(("plan", index), found)
        return violations


class InstrumentState(InstrumentPreset):
    """Saved state that the operator edits: a preset plus specimen metadata and the time it last changed."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    last_modified: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.UTC))


def new_instrument_id() -> str:
    value = secrets.randbits(128)
    return "".join(_ID_ALPHABET[(value >> shift) & 31] for shift in range(125, -1, -5))


def _file_violations(hal: HALConfig, engine: "Engine[Any]", default: InstrumentDefaults) -> list[Violation]:
    return [
        *under(("hal",), hal.violations()),
        *under(("engine",), engine.violations()),
        *under(("default",), default.violations(hal, engine)),
    ]


class InstrumentTemplate(FrozenModel):
    """A shipped instrument design: an instrument file without an ID or a name."""

    model: InstrumentModel | None = None
    hal: HALConfig
    engine: EngineConfig
    default: InstrumentDefaults

    def instantiate(self, name: str) -> "InstrumentConfig":
        """Make a new instrument from this design, with a new ID."""
        return InstrumentConfig.model_validate({"id": new_instrument_id(), "name": name, **dict(self)})

    def violations(self, engine: "Engine[Any]") -> list[Violation]:
        """Return the problems that the file shows. ``engine`` is the engine that the file names."""
        return _file_violations(self.hal, engine, self.default)


class InstrumentConfig(FrozenModel):
    """An instrument's ``config.yaml``. Its ID is made when the instrument is created and never changes."""

    id: InstrumentId
    name: InstrumentName
    model: InstrumentModel | None = None
    hal: HALConfig
    engine: EngineConfig
    default: InstrumentDefaults

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and validate 1 instrument file."""
        return cls.model_validate(YAML(typ="safe").load(path.read_text(encoding="utf-8")))

    def violations(self, engine: "Engine[Any]") -> list[Violation]:
        """Return the problems that the file shows. ``engine`` is the engine that the file names."""
        return _file_violations(self.hal, engine, self.default)


__all__ = [
    "InstrumentConfig",
    "InstrumentDefaults",
    "InstrumentId",
    "InstrumentModel",
    "InstrumentName",
    "InstrumentPreset",
    "InstrumentState",
    "InstrumentTemplate",
    "held_by_instrument",
    "new_instrument_id",
]
