"""The files of 1 instrument: ``config.yaml`` and ``state.json``."""

import asyncio
import datetime
from collections.abc import Collection
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ValidationError
from vxlib.reactivity import Cell, Readable, Subscribable
from vxlib.schema import error_message

from vxl._utils.files import atomic_write, load_and_validate_yaml, save_yaml
from vxl.hal_next.errors import StartupError, Violation

from .config import InstrumentConfig, InstrumentDefaults, InstrumentPreset, InstrumentState

PROMOTABLE_FIELDS = frozenset(InstrumentDefaults.model_fields)
"""The fields that can move between the state and the instrument's defaults."""


class OperationRejectedError(Exception):
    """A request that the instrument refuses, such as an edit that does not validate."""


class InstrumentStore(Subscribable[InstrumentState]):
    """The files of 1 instrument. Each change to the state is validated, saved, and sent to the subscribers."""

    @staticmethod
    def instantiate(config: InstrumentConfig, name: str, into: Path | str) -> Path:
        """Create ``<into>/<name>.voxel`` and save its ``config.yaml``."""
        directory = Path(into) / f"{name}.voxel"
        if directory.exists():
            raise FileExistsError(f"Instrument '{name}' already exists at {directory}")
        directory.mkdir(parents=True)
        save_yaml(directory / "config.yaml", config)
        return directory

    @classmethod
    def load(cls, home: Path | str) -> Self:
        """Read ``config.yaml`` and ``state.json``. A missing ``state.json`` starts from ``config.default``. Raise
        :class:`StartupError` when a file is missing or does not validate."""
        home = Path(home)
        config, violations = _read(home / "config.yaml", InstrumentConfig, "config")
        if config is None and not violations:
            violations = [
                Violation(
                    code="config.missing", msg=f"No InstrumentConfig found at {home / 'config.yaml'}", loc=("config",)
                )
            ]
        state, state_violations = _read(home / "state.json", InstrumentState, "state")
        violations += state_violations
        if violations or config is None:
            raise StartupError(violations)
        if state is None:
            state = InstrumentState.model_validate(config.default.model_dump())
        return cls(home, config, state)

    def __init__(self, home: Path, config: InstrumentConfig, state: InstrumentState) -> None:
        super().__init__()
        self._home = home
        self._config = config
        self._value = state
        self._default = Cell(config.default)
        self._lock = asyncio.Lock()

    @property
    def home(self) -> Path:
        return self._home

    @property
    def config(self) -> InstrumentConfig:
        return self._config

    @property
    def default(self) -> Readable[InstrumentDefaults]:
        return self._default

    @property
    def value(self) -> InstrumentState:
        """The saved state. It is frozen, so it is safe to hand out."""
        return self._value

    async def set(self, candidate: InstrumentState) -> None:
        """Validate, save and adopt ``candidate``. An unchanged state is dropped: no save, no notification. Raise
        :class:`OperationRejectedError` when it does not validate."""
        async with self._lock:
            await self._commit(candidate)

    async def update(self, **updates: Any) -> None:
        """Change top-level fields of the state, as :meth:`set` does."""
        async with self._lock:
            await self._commit(self._value.model_copy(update=updates))

    async def save_as_default(self, include: Collection[str] = PROMOTABLE_FIELDS) -> None:
        """Save the given fields of the state as the instrument's defaults, in ``config.yaml``."""
        fields = set(include)
        if unknown := fields - PROMOTABLE_FIELDS:
            raise OperationRejectedError(f"Cannot promote non-default fields: {sorted(unknown)}")
        async with self._lock:
            default = self._default.value.model_copy(update={field: getattr(self._value, field) for field in fields})
            config = self._config.model_copy(update={"default": default})
            await asyncio.to_thread(save_yaml, self._home / "config.yaml", config)
            self._config = config
            await self._default.set(default)

    async def restore_default(self, include: Collection[str] = PROMOTABLE_FIELDS) -> None:
        """Set the given fields of the state back to the instrument's defaults."""
        fields = set(include)
        if unknown := fields - PROMOTABLE_FIELDS:
            raise OperationRejectedError(f"Cannot restore non-default fields: {sorted(unknown)}")
        async with self._lock:
            default = self._default.value
            await self._commit(self._value.model_copy(update={field: getattr(default, field) for field in fields}))

    async def apply_preset(self, preset: InstrumentPreset) -> None:
        """Replace the reusable fields of the state. The specimen metadata stays when its schema does not change."""
        async with self._lock:
            metadata = self._value.metadata if preset.metadata_cls == self._value.metadata_cls else {}
            candidate = InstrumentState.model_validate(
                {**preset.model_dump(), "metadata": metadata, "last_modified": self._value.last_modified}
            )
            await self._commit(candidate)

    async def _commit(self, candidate: InstrumentState) -> None:
        try:
            validated = InstrumentState.model_validate(candidate.model_dump())
        except ValidationError as exc:
            raise OperationRejectedError("; ".join(error["msg"] for error in exc.errors())) from exc
        if validated.model_copy(update={"last_modified": self._value.last_modified}) == self._value:
            return
        stamped = validated.model_copy(update={"last_modified": datetime.datetime.now(tz=datetime.UTC)})
        await asyncio.to_thread(
            atomic_write, self._home / "state.json", stamped.model_dump_json(indent=2, exclude_none=True)
        )
        self._value = stamped
        await self._notify(stamped)


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
