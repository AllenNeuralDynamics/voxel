"""An instrument's folder: ``rig.yaml``, ``default.yaml`` and ``state.json``, and the class that runs them."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from rigup.build import import_class
from vxlib.issues import Problems

from vxl._utils.files import load_yaml, update_yaml
from vxl.records import Records
from vxl.station.errors import RejectedError, StartupError
from vxl.station.instrument.base import Instrument
from vxl.station.instrument.config import InstrumentConfig, new_instrument_id
from vxl.station.instrument.state import InstrumentState
from vxl.system import System


@dataclass(frozen=True)
class InstrumentFolder[C: InstrumentConfig, S: InstrumentState]:
    """An instrument's folder, read with no hardware. ``kind`` is the class that runs it: the ``target`` of
    ``rig.yaml``. The files are read with the config and state classes of that class. ``kind``, ``config``,
    ``default`` or ``state`` is ``None`` when it cannot be read. A missing ``state.json`` is not a problem: the
    instrument starts from its defaults. A missing ``default.yaml`` counts as an empty one. ``C`` and ``S`` are the
    config and state classes; a folder read from disk has them only when the program runs."""

    home: Path
    kind: type[Instrument[C, S]] | None
    config: C | None
    default: S | None
    state: S | None
    problems: Problems

    @property
    def ok(self) -> bool:
        """Whether the instrument can be built."""
        return self.config is not None and self.default is not None and not self.problems

    @staticmethod
    def read(home: Path | str) -> "InstrumentFolder[Any, Any]":
        """Read the folder at ``home``. Return each problem; do not raise."""
        home = Path(home)
        rig, problems = _load(home / "rig.yaml", "rig")
        if rig is None and not problems:
            problems.add("rig.missing", f"No instrument file found at {home / 'rig.yaml'}", "rig")
        if rig is None:
            return InstrumentFolder(home, None, None, None, None, problems)
        try:
            kind = InstrumentFolder._kind(rig)
        except ValueError as error:
            problems.add("rig.target", str(error), "rig", "target")
            return InstrumentFolder(home, None, None, None, None, problems)

        config, problems = _validate(rig, kind.config_cls, "rig")
        if config is None:
            return InstrumentFolder(home, kind, None, None, None, problems)
        problems += config.problems().under("rig")

        default, found = _read(home / "default.yaml", kind.state_cls, "default", missing={})
        problems += found
        if default is not None:
            for name in sorted(default.model_fields_set - default.default_fields()):
                problems.add("default.not_default", f"'{name}' is not saved as a default.", "default", name)
            problems += default.problems(config).under("default")

        state, found = _read(home / "state.json", kind.state_cls, "state")
        problems += found
        if state is not None:
            problems += state.problems(config).under("state")
        return InstrumentFolder(home, kind, config, default, state, problems)

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


def _read[T: BaseModel](
    path: Path, model: type[T], source: str, *, missing: Mapping[str, Any] | None = None
) -> tuple[T | None, Problems]:
    """Read and validate 1 file, as :func:`_load` and :func:`_validate` do."""
    data, problems = _load(path, source, missing=missing)
    if data is None:
        return None, problems
    return _validate(data, model, source)


__all__ = ["InstrumentFolder"]
