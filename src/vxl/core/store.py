"""The files of 1 instrument: ``config.yaml`` and ``state.json``."""

import asyncio
import datetime
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ValidationError
from vxlib.reactivity import Cell, Readable, Subscribable
from vxlib.schema import error_message

from vxl._utils.files import atomic_write, load_and_validate_yaml, save_yaml
from vxl.hal_next.errors import StartupError, Violation, under

from .config import InstrumentConfig, InstrumentState


class OperationRejectedError(Exception):
    """A request that the instrument refuses, such as an edit that does not validate."""


@dataclass(frozen=True)
class InstrumentInspection[C: InstrumentConfig[Any, Any], S: InstrumentState[Any]]:
    """What is in an instrument's folder. ``config`` or ``state`` is ``None`` when its file is missing or does not
    validate. A missing ``state.json`` is not a problem."""

    config: C | None
    state: S | None
    violations: list[Violation]

    @property
    def ok(self) -> bool:
        """Whether the instrument can be loaded."""
        return self.config is not None and not self.violations


class InstrumentStore[C: InstrumentConfig[Any, Any], S: InstrumentState[Any]](Subscribable[S]):
    """The files of 1 instrument. Each change to the state is validated, saved, and sent to the subscribers."""

    @staticmethod
    def instantiate(config: InstrumentConfig[Any, Any], name: str, into: Path | str) -> Path:
        """Create ``<into>/<name>.voxel`` and save its ``config.yaml``."""
        directory = Path(into) / f"{name}.voxel"
        if directory.exists():
            raise FileExistsError(f"Instrument '{name}' already exists at {directory}")
        directory.mkdir(parents=True)
        save_yaml(directory / "config.yaml", config)
        return directory

    @classmethod
    def check(cls, home: Path | str, config_cls: type[C]) -> InstrumentInspection[C, S]:
        """Read ``config.yaml`` and ``state.json`` with no hardware. Return each problem; do not raise."""
        home = Path(home)
        state_cls: type[S] = config_cls.state_class()
        config, violations = _read(home / "config.yaml", config_cls, "config")
        if config is None and not violations:
            msg = f"No instrument file found at {home / 'config.yaml'}"
            violations = [Violation(code="config.missing", msg=msg, loc=("config",))]
        if config is not None:
            violations += under(("config",), config.violations())
        state, state_violations = _read(home / "state.json", state_cls, "state")
        violations += state_violations
        if config is not None and state is not None:
            violations += under(("state",), state.violations(config.hal))
        return InstrumentInspection(config, state, violations)

    @classmethod
    def load(cls, home: Path | str, config_cls: type[C]) -> Self:
        """Read ``config.yaml`` and ``state.json``. A missing ``state.json`` starts from ``config.default``. Raise
        :class:`StartupError` when a file is missing or has a problem."""
        home = Path(home)
        found: InstrumentInspection[C, S] = cls.check(home, config_cls)
        if found.config is None or found.violations:
            raise StartupError(found.violations)
        if found.state is None:
            return cls(home, found.config, found.config.default, last_modified=None)
        saved = datetime.datetime.fromtimestamp((home / "state.json").stat().st_mtime, tz=datetime.UTC)
        return cls(home, found.config, found.state, last_modified=saved)

    def __init__(self, home: Path, config: C, state: S, *, last_modified: datetime.datetime | None) -> None:
        super().__init__()
        self._home = home
        self._config = config
        self._value = state
        self._last_modified = last_modified
        self._default: Cell[S] = Cell(config.default)
        self._lock = asyncio.Lock()

    @property
    def home(self) -> Path:
        return self._home

    @property
    def config(self) -> C:
        return self._config

    @property
    def default(self) -> Readable[S]:
        return self._default

    @property
    def value(self) -> S:
        """The saved state. It is frozen, so it is safe to hand out."""
        return self._value

    @property
    def last_modified(self) -> datetime.datetime | None:
        """When the state was last saved, or ``None`` when it never was."""
        return self._last_modified

    async def set(self, candidate: S) -> None:
        """Validate, save and adopt ``candidate``. An unchanged state is dropped: no save, no notification. Raise
        :class:`OperationRejectedError` when it does not validate."""
        async with self._lock:
            await self._commit(candidate)

    async def update(self, **updates: Any) -> None:
        """Change top-level fields of the state, as :meth:`set` does."""
        async with self._lock:
            await self._commit(self._value.model_copy(update=updates))

    async def save_as_default(self, include: Collection[str] | None = None) -> None:
        """Save the given fields of the state as the instrument's defaults, in ``config.yaml``. With no fields
        given, save each field that can be a default."""
        fields = self._default_fields(include, "save as default")
        async with self._lock:
            default = self._default.value.model_copy(update={field: getattr(self._value, field) for field in fields})
            config = self._config.model_copy(update={"default": default})
            await asyncio.to_thread(save_yaml, self._home / "config.yaml", config)
            self._config = config
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
        await asyncio.to_thread(
            atomic_write, self._home / "state.json", validated.model_dump_json(indent=2, exclude_none=True)
        )
        self._value = validated
        self._last_modified = datetime.datetime.now(tz=datetime.UTC)
        await self._notify(validated)


def _read[T: BaseModel](path: Path, model: type[T], source: str) -> tuple[T | None, list[Violation]]:
    """Read and validate 1 file. The value is ``None`` when the file is missing or wrong."""
    try:
        return load_and_validate_yaml(path, model), []
    except FileNotFoundError:
        return None, []
    except ValidationError as exc:
        return None, [
            Violation(code=f"{source}.{error['type']}", msg=error_message(error), loc=(source, *error["loc"]))
            for error in exc.errors()
        ]
    except Exception as exc:
        return None, [Violation(code=f"{source}.load", msg=str(exc), loc=(source,))]
