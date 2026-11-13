"""The saved state of 1 running instrument: ``state.json``, and its defaults in ``default.yaml``."""

import asyncio
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from vxlib.history import Change
from vxlib.problems import KeyPath, Problems
from vxlib.reactivity import Cell, Readable, Subscribable

from vxl._utils.files import atomic_write, update_yaml
from vxl.core.errors import RejectedError
from vxl.core.instrument.config import InstrumentConfig, InstrumentState


class Absent(Enum):
    """No value at a key path: the key is not there. Setting it removes the key."""

    ABSENT = "absent"


ABSENT = Absent.ABSENT


@dataclass(frozen=True)
class Merge:
    """Keys to add to the dict at a key path, or to replace there; its other keys stay. The dict is made when the key
    is not there, but the rest of the path must be there."""

    values: Mapping[str, Any]


type StateValues = Mapping[KeyPath, Any]
"""A value for each key path of the state."""

type StateChange = Change[dict[KeyPath, Any]]
"""The values at each key path of the state, before and after an update."""


class InstrumentStore[S: InstrumentState](Subscribable[S]):
    """The saved state of 1 running instrument. Each change is checked against ``rig.yaml``, saved in
    ``state.json``, and sent to the subscribers. Only the instrument holds it."""

    def __init__(self, home: Path, config: InstrumentConfig, default: S, state: S) -> None:
        super().__init__()
        self._home = home
        self._config = config
        self._value = state
        saved = home / "state.json"
        self._last_modified = datetime.fromtimestamp(saved.stat().st_mtime, tz=UTC) if saved.is_file() else None
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
    def default_state(self) -> Readable[S]:
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
        :class:`RejectedError` when it has a problem."""
        async with self._lock:
            await self._commit(candidate.model_dump())

    async def update(self, values: StateValues) -> StateChange:
        """Set the value at each key path of the state, as :meth:`set` does, and give the values before and after.
        :data:`ABSENT` removes a key, and is the value of a key that is not there. :class:`Merge` adds keys to a dict.
        Raise :class:`RejectedError` when a path leads to nothing, or a merge meets something that is not a dict."""
        async with self._lock:
            data = self._value.model_dump()
            before: dict[KeyPath, Any] = {}
            for path, value in values.items():
                parent, key, before[path] = self._find(data, path)
                match value, before[path]:
                    case Absent(), _:
                        parent.pop(key, None)
                    case Merge(), Absent():
                        parent[key] = dict(value.values)
                    case Merge(), dict() as current:
                        parent[key] = current | dict(value.values)
                    case Merge(), _:
                        problems = Problems()
                        msg = f"'{'.'.join(map(str, path))}' holds no keys to merge into."
                        problems.add("state.not_a_dict", msg, *path)
                        raise RejectedError(str(problems), problems)
                    case _:
                        parent[key] = value
            await self._commit(data)
            saved = self._value.model_dump()
            return Change(before=before, after={path: self._find(saved, path)[2] for path in values})

    async def save_as_default_state(self, include: Collection[str] | None = None) -> None:
        """Save the given fields of the state as the instrument's defaults, in ``default.yaml``. With no fields
        given, save each field that can be a default."""
        fields = self._default_fields(include, "save as default")
        async with self._lock:
            default = self._default.value.model_copy(update={field: getattr(self._value, field) for field in fields})
            if found := default.problems(self._config):
                raise RejectedError(f"Cannot save as default: {found}", found)
            data = default.model_dump(mode="json", exclude_none=True, include=set(default.default_fields()))
            await asyncio.to_thread(update_yaml, self._home / "default.yaml", data)
            await self._default.set(default)

    def default_values(self, include: Collection[str] | None = None) -> dict[KeyPath, Any]:
        """The value of the given fields in the default state, or of each field that can be a default, as
        :meth:`update` takes them."""
        default = self._default.value.model_dump()
        return {(field,): default[field] for field in sorted(self._default_fields(include, "restore"))}

    def _default_fields(self, include: Collection[str] | None, action: str) -> frozenset[str]:
        allowed = self._value.default_fields()
        if include is None:
            return allowed
        if unknown := set(include) - allowed:
            raise RejectedError(f"Cannot {action}: {sorted(unknown)} cannot be a default")
        return frozenset(include)

    @staticmethod
    def _find(data: Any, path: KeyPath) -> tuple[Any, str | int, Any]:
        """In plain ``data``: the container that holds the last key of ``path``, that key, and its value."""
        *parents, last = path
        try:
            for key in parents:
                data = data[key]
            value = data.get(last, ABSENT) if isinstance(data, dict) else data[last]
        except (KeyError, IndexError, TypeError) as error:
            problems = Problems()
            problems.add("state.missing", f"Nothing at '{'.'.join(map(str, path))}'.", *path)
            raise RejectedError(str(problems), problems) from error
        return data, last, value

    async def _commit(self, data: dict[str, Any]) -> None:
        try:
            validated = self._value.model_validate(data)
        except ValidationError as exc:
            problems = Problems.from_validation(exc)
            raise RejectedError(str(problems), problems) from exc
        if validated == self._value:
            return
        if found := validated.problems(self._config):
            raise RejectedError(str(found), found)
        await asyncio.to_thread(
            atomic_write, self._home / "state.json", validated.model_dump_json(indent=2, exclude_none=True)
        )
        self._value = validated
        self._last_modified = datetime.now(tz=UTC)
        await self._notify(validated)
