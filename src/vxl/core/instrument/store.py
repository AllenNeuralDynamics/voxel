"""The files of 1 instrument: ``rig.yaml``, ``default.yaml`` and ``state.json``."""

import asyncio
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ValidationError
from vxlib.reactivity import Cell, Readable, Subscribable

from vxl._utils.files import atomic_write, load_yaml, update_yaml

from .config import InstrumentConfig, InstrumentState, new_instrument_id
from .errors import StartupError, Violations


class OperationRejectedError(Exception):
    """A request that the instrument refuses, such as an edit that does not validate."""


@dataclass(frozen=True)
class InstrumentInspection:
    """What is in an instrument's folder. ``config``, ``default`` or ``state`` is ``None`` when its file does not
    validate. A missing ``state.json`` is not a problem, and a missing ``default.yaml`` counts as an empty one."""

    home: Path
    config: InstrumentConfig | None
    default: InstrumentState | None
    state: InstrumentState | None
    violations: Violations

    @property
    def ok(self) -> bool:
        """Whether the instrument can be loaded."""
        return self.config is not None and not self.violations


class InstrumentStore[S: InstrumentState](Subscribable[S]):
    """The files of 1 instrument. Each change to the state is checked against ``rig.yaml``, saved, and sent to the
    subscribers."""

    @staticmethod
    def create(template: Mapping[str, Any], name: str, into: Path | str) -> Path:
        """Make ``<into>/<name>.voxel`` from a template. A template has 2 keys: ``rig`` is a ``rig.yaml`` without
        an ID or a name, and ``default`` is the ``default.yaml``."""
        if set(template) != {"rig", "default"}:
            raise ValueError("a template has 2 keys: 'rig' and 'default'")
        rig = template["rig"]
        if given := sorted({"id", "name"} & set(rig)):
            raise ValueError(f"a template has no {' and no '.join(given)}")
        directory = Path(into) / f"{name}.voxel"
        if directory.exists():
            raise FileExistsError(f"Instrument '{name}' already exists at {directory}")
        directory.mkdir(parents=True)
        update_yaml(directory / "rig.yaml", {"id": new_instrument_id(), "name": name, **rig})
        update_yaml(directory / "default.yaml", template["default"])
        return directory

    @staticmethod
    def check(
        home: Path | str, config_cls: type[InstrumentConfig], state_cls: type[InstrumentState]
    ) -> InstrumentInspection:
        """Read ``rig.yaml``, ``default.yaml`` and ``state.json`` with no hardware. Return each problem; do not
        raise."""
        home = Path(home)
        config, violations = _read(home / "rig.yaml", config_cls, "rig")
        if config is None and not violations:
            violations.add("rig.missing", f"No instrument file found at {home / 'rig.yaml'}", "rig")
        if config is None:
            return InstrumentInspection(home, None, None, None, violations)
        violations += config.violations().under("rig")
        default, found = _read(home / "default.yaml", state_cls, "default", missing={})
        violations += found
        if default is not None:
            for name in sorted(default.model_fields_set - default.default_fields()):
                violations.add("default.not_default", f"'{name}' is not saved as a default.", "default", name)
            violations += default.violations(config).under("default")
        state, found = _read(home / "state.json", state_cls, "state")
        violations += found
        if state is not None:
            violations += state.violations(config).under("state")
        return InstrumentInspection(home, config, default, state, violations)

    @classmethod
    def from_inspection(cls, found: InstrumentInspection, state_cls: type[S]) -> Self:
        """The store of a checked instrument. A missing ``state.json`` starts from the defaults. Raise
        :class:`StartupError` when the instrument has a problem."""
        if found.config is None or found.default is None or found.violations:
            raise StartupError(found.violations)
        default, state = found.default, found.state or found.default
        if not isinstance(default, state_cls) or not isinstance(state, state_cls):
            raise TypeError(f"the instrument at {found.home} was not checked as {state_cls.__name__}")
        saved: datetime | None = None
        if found.state is not None:
            saved = datetime.fromtimestamp((found.home / "state.json").stat().st_mtime, tz=UTC)
        return cls(found.home, found.config, default, state, last_modified=saved)

    def __init__(
        self, home: Path, config: InstrumentConfig, default: S, state: S, *, last_modified: datetime | None = None
    ) -> None:
        super().__init__()
        self._home = home
        self._config = config
        self._value = state
        self._last_modified = last_modified
        self._default: Cell[S] = Cell(default)
        self._lock = asyncio.Lock()

    @property
    def home(self) -> Path:
        return self._home

    @property
    def config(self) -> InstrumentConfig:
        """The ``rig.yaml`` of the instrument."""
        return self._config

    @property
    def default(self) -> Readable[S]:
        return self._default

    @property
    def value(self) -> S:
        """The saved state. It is frozen, so it is safe to hand out."""
        return self._value

    @property
    def last_modified(self) -> datetime | None:
        """When the state was last saved, or ``None`` when it never was."""
        return self._last_modified

    async def set(self, candidate: S) -> None:
        """Check, save and adopt ``candidate``. An unchanged state is dropped: no save, no notification. Raise
        :class:`OperationRejectedError` when it has a problem."""
        async with self._lock:
            await self._commit(candidate)

    async def update(self, **updates: Any) -> None:
        """Change top-level fields of the state, as :meth:`set` does."""
        async with self._lock:
            await self._commit(self._value.model_copy(update=updates))

    async def save_as_default(self, include: Collection[str] | None = None) -> None:
        """Save the given fields of the state as the instrument's defaults, in ``default.yaml``. With no fields
        given, save each field that can be a default."""
        fields = self._default_fields(include, "save as default")
        async with self._lock:
            default = self._default.value.model_copy(update={field: getattr(self._value, field) for field in fields})
            if found := default.violations(self._config):
                raise OperationRejectedError(f"Cannot save as default: {found}")
            data = default.model_dump(mode="json", exclude_none=True, include=set(default.default_fields()))
            await asyncio.to_thread(update_yaml, self._home / "default.yaml", data)
            await self._default.set(default)

    async def restore_default(self, include: Collection[str] | None = None) -> None:
        """Set the given fields of the state back to the instrument's defaults. With no fields given, set back
        each field that can be a default."""
        fields = self._default_fields(include, "restore")
        async with self._lock:
            default = self._default.value
            await self._commit(self._value.model_copy(update={field: getattr(default, field) for field in fields}))

    async def apply_preset(self, preset: S) -> None:
        """Replace the state with ``preset``. The specimen metadata stays when its form does not change."""
        async with self._lock:
            metadata = self._value.metadata if preset.metadata_cls == self._value.metadata_cls else {}
            await self._commit(preset.model_copy(update={"metadata": metadata}))

    def _default_fields(self, include: Collection[str] | None, action: str) -> frozenset[str]:
        allowed = type(self._value).default_fields()
        if include is None:
            return allowed
        if unknown := set(include) - allowed:
            raise OperationRejectedError(f"Cannot {action}: {sorted(unknown)} cannot be a default")
        return frozenset(include)

    async def _commit(self, candidate: S) -> None:
        try:
            validated = type(self._value).model_validate(candidate.model_dump())
        except ValidationError as exc:
            raise OperationRejectedError("; ".join(error["msg"] for error in exc.errors())) from exc
        if validated == self._value:
            return
        if found := validated.violations(self._config):
            raise OperationRejectedError(str(found))
        await asyncio.to_thread(
            atomic_write, self._home / "state.json", validated.model_dump_json(indent=2, exclude_none=True)
        )
        self._value = validated
        self._last_modified = datetime.now(tz=UTC)
        await self._notify(validated)


def _read[T: BaseModel](
    path: Path, model: type[T], source: str, *, missing: Mapping[str, Any] | None = None
) -> tuple[T | None, Violations]:
    """Read and validate 1 file. The value is ``None`` when the file is wrong. A file that is not there reads as
    ``missing``, and the value is ``None`` when no ``missing`` is given."""
    try:
        data = load_yaml(path)
    except FileNotFoundError:
        if missing is None:
            return None, Violations()
        data = missing
    except Exception as error:
        found = Violations()
        found.add(f"{source}.load", str(error), source)
        return None, found
    try:
        return model.model_validate(data), Violations()
    except ValidationError as error:
        return None, Violations.from_validation(error, source)
