"""An instrument's folder: ``rig.yaml``, ``default.yaml`` and ``state.json``, and the class that runs them."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, SerializeAsAny, ValidationError
from rigup.build import import_class
from vxlib.issues import Level, Problem, Problems
from vxlib.schema import FrozenModel

from vxl._utils.files import load_yaml, update_yaml
from vxl.instrument.base import Instrument
from vxl.instrument.config import InstrumentConfig, new_instrument_id
from vxl.instrument.state import InstrumentState
from vxl.records import Records
from vxl.station.errors import RejectedError, StartupError
from vxl.system import System


class FolderFile[T: BaseModel](FrozenModel):
    """1 file of an instrument's folder: its content as read, and the same content as its model. ``data`` is
    ``None`` for a file that cannot be read, and for one that is not there. ``model`` is ``None`` until the content
    passes its checks: it has a problem, or the file it is checked against has one. A file with content, no model
    and no problem was not checked. A file with no content and no problem is not on disk."""

    data: Any
    model: SerializeAsAny[T] | None = None


class InstrumentInspection(TypedDict):
    """What a client gets of an instrument's folder: each problem at its place. The instrument can be built when no
    problem is fatal. The full form has ``files``: ``rig``, ``default`` and ``state``, each with its content and
    its model."""

    problems: list[Problem]
    files: NotRequired[dict[str, FolderFile[Any]]]


@dataclass(frozen=True)
class InstrumentFolder[C: InstrumentConfig, S: InstrumentState]:
    """An instrument's folder, read with no hardware. ``kind`` is the class that runs it: the ``target`` of
    ``rig.yaml``, or ``None`` when it names none. ``rig``, ``default`` and ``state`` are its 3 files, read with the
    config and state classes of that class. A missing ``state.json`` is not a problem: the instrument starts from
    its defaults. A missing ``default.yaml`` counts as an empty one. ``C`` and ``S`` are the config and state
    classes; a folder read from disk has them only when the program runs."""

    home: Path
    kind: type[Instrument[C, S]] | None
    rig: FolderFile[C]
    default: FolderFile[S]
    state: FolderFile[S]
    problems: Problems

    @property
    def name(self) -> str:
        """The name of the instrument: the folder's name without ``.voxel``."""
        return self.home.stem

    @property
    def ok(self) -> bool:
        """Whether the instrument can be built: no problem is fatal."""
        return self.rig.model is not None and self.default.model is not None and not self.problems.fatal()

    def inspection(self, *, files: bool = False) -> InstrumentInspection:
        """The folder as a client gets it, with the content of its files when ``files`` is set."""
        found = InstrumentInspection(problems=list(self.problems))
        if files:
            found["files"] = {"rig": self.rig, "default": self.default, "state": self.state}
        return found

    @staticmethod
    def read(home: Path | str) -> "InstrumentFolder[Any, Any]":
        """Read the folder at ``home``. Return each problem; do not raise. Every file is read, also when one before
        it has a problem; a file is checked only when the files it is checked against are in order. Every problem of
        the rig and the defaults is fatal, and so is a file that cannot be read or does not pass its checks: the
        instrument would start without it. The state's own checks set their levels."""
        home = Path(home)
        rig, problems = _load(home / "rig.yaml", "rig")
        if rig is None and not problems:
            problems.add("rig.missing", f"No instrument file found at {home / 'rig.yaml'}", "rig")
        default, default_problems = _load(home / "default.yaml", "default", missing={})
        state, state_problems = _load(home / "state.json", "state")

        kind: type[Instrument[Any, Any]] | None = None
        config: InstrumentConfig | None = None
        default_model: InstrumentState | None = None
        state_model: InstrumentState | None = None
        if rig is not None:
            try:
                kind = InstrumentFolder._kind(rig)
            except ValueError as error:
                problems.add("rig.target", str(error), "rig", "target")
        if kind is not None:
            config, found = _validate(rig, kind.config_cls, "rig")
            problems += found
        if config is not None:
            problems += config.problems().under("rig")
        problems = problems.as_fatal()
        problems += default_problems.as_fatal()
        if kind is not None and config is not None and default is not None:
            default_model, found = _validate(default, kind.state_cls, "default")
            problems += found.as_fatal()
            if default_model is not None:
                for name in sorted(default_model.model_fields_set - default_model.default_fields()):
                    msg = f"'{name}' is not saved as a default."
                    problems.add("default.not_default", msg, "default", name, level=Level.FATAL)
                problems += default_model.problems(config).under("default").as_fatal()
        problems += state_problems.as_fatal()
        if kind is not None and config is not None and state is not None:
            state_model, found = _validate(state, kind.state_cls, "state")
            problems += found.as_fatal()
            if state_model is not None:
                problems += state_model.problems(config).under("state")
        return InstrumentFolder(
            home,
            kind,
            FolderFile(data=rig, model=config),
            FolderFile(data=default, model=default_model),
            FolderFile(data=state, model=state_model),
            problems,
        )

    @staticmethod
    def create(template: Mapping[str, Any], name: str, into: Path | str) -> "InstrumentFolder[Any, Any]":
        """Make ``<into>/<name>.voxel`` from a template, and read it. A template has 2 keys: ``rig`` is a
        ``rig.yaml`` without an ID or a name, and ``default`` is the ``default.yaml``."""
        if set(template) != {"rig", "default"}:
            raise RejectedError("a template has 2 keys: 'rig' and 'default'")
        rig = template["rig"]
        if given := sorted({"id", "name"} & set(rig)):
            raise RejectedError(f"a template has no {' and no '.join(given)}")
        home = Path(into) / f"{name}.voxel"
        if home.exists():
            raise RejectedError(f"Instrument '{name}' already exists at {home}")
        home.mkdir(parents=True)
        update_yaml(home / "rig.yaml", {"id": new_instrument_id(), "name": name, **rig})
        update_yaml(home / "default.yaml", template["default"])
        return InstrumentFolder.read(home)

    def instrument(self, *, records: Records, system: System) -> Instrument[C, S]:
        """The instrument of this folder, of its kind, without opening hardware. Raise :class:`StartupError` when
        the folder has a problem."""
        if self.kind is None:
            raise StartupError(self.problems)
        return self.kind(self, records=records, system=system)

    @staticmethod
    def _kind(rig: object) -> type[Instrument[Any, Any]]:
        """The class that the ``target`` of a ``rig.yaml`` names. Raise :class:`ValueError` when it names none, or
        a class that cannot run an instrument."""
        target = rig.get("target") if isinstance(rig, dict) else None
        if not isinstance(target, str):
            raise ValueError("rig.yaml names no target")
        kind = import_class(target, Instrument)
        if not hasattr(kind, "config_cls"):
            raise ValueError(f"'{target}' names no config and state classes")
        return kind


def _load(path: Path, source: str, *, missing: Mapping[str, Any] | None = None) -> tuple[Any, Problems]:
    """The data of 1 file, or ``None`` with its problem. A file that is not there reads as ``missing``, and as
    ``None`` with no problem when no ``missing`` is given."""
    try:
        return load_yaml(path), Problems()
    except FileNotFoundError:
        return missing, Problems()
    except Exception as error:
        found = Problems()
        found.add(f"{source}.load", str(error), source)
        return None, found


def _validate[T: BaseModel](data: Any, model: type[T], source: str) -> tuple[T | None, Problems]:
    """``data`` as a ``model``, or ``None`` with its problems."""
    try:
        return model.model_validate(data), Problems()
    except ValidationError as error:
        return None, Problems.from_validation(error, source)


__all__ = ["FolderFile", "InstrumentFolder", "InstrumentInspection"]
