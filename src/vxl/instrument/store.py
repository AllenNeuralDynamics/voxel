"""The saved state of 1 running instrument: ``state.json``, and its defaults in ``default.yaml``."""

import asyncio
import shutil
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from vxlib.history import Change
from vxlib.issues import KeyPath, Problems
from vxlib.reactivity import Cell, Readable, Subscribable

from vxl._utils.files import atomic_write, update_yaml
from vxl.instrument.config import InstrumentConfig
from vxl.instrument.state import InstrumentState
from vxl.station.errors import RejectedError


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
    ``state.json``, and sent to the subscribers. Only the instrument holds it. Before ``default.yaml`` changes, the
    file is copied into ``backups``, with the date and time in its name; the folder keeps the newest
    ``DEFAULT_BACKUPS`` copies."""

    DEFAULT_BACKUPS = 5

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

    async def save_as_default_state(self, paths: Collection[KeyPath] | None = None) -> None:
        """Save the value of the state at each key path as the instrument's default there, in ``default.yaml``. With
        no paths given, save each field that can be a default. A key that the state does not have leaves the
        defaults. Raise :class:`RejectedError` when the defaults would have a problem; then nothing is saved."""
        paths = self._default_paths(paths, "save as default")
        async with self._lock:
            data, state = self._default.value.model_dump(), self._value.model_dump()
            for path in paths:
                parent, key, _ = self._find(data, path)
                value = self._find(state, path)[2]
                if isinstance(value, Absent):
                    parent.pop(key, None)
                else:
                    parent[key] = value
            try:
                default = self._default.value.model_validate(data)
            except ValidationError as exc:
                problems = Problems.from_validation(exc)
                raise RejectedError(f"Cannot save as default: {problems}", problems) from exc
            if default == self._default.value:
                return
            if found := default.problems(self._config).errors():
                raise RejectedError(f"Cannot save as default: {found}", found)
            saved = default.model_dump(mode="json", exclude_none=True, include=set(default.default_fields()))
            await asyncio.to_thread(self._write_default, saved)
            await self._default.set(default)

    def default_values(self, paths: Collection[KeyPath] | None = None) -> dict[KeyPath, Any]:
        """The value of the default state at each key path, or of each field that can be a default, as
        :meth:`update` takes them: :data:`ABSENT` for a key that the defaults do not have."""
        default = self._default.value.model_dump()
        return {path: self._find(default, path)[2] for path in self._default_paths(paths, "restore")}

    def _default_paths(self, paths: Collection[KeyPath] | None, action: str) -> list[KeyPath]:
        """``paths``, or 1 path for each field that can be a default. Raise :class:`RejectedError` for a path that
        starts at no such field."""
        allowed = self._value.default_fields()
        if paths is None:
            return [(field,) for field in sorted(allowed)]
        found = [tuple(path) for path in paths]
        if unknown := sorted({str(path[0]) if path else "" for path in found if not path or path[0] not in allowed}):
            raise RejectedError(f"Cannot {action}: {unknown} cannot be a default")
        return found

    def _write_default(self, data: Mapping[str, Any]) -> None:
        """Copy ``default.yaml`` into ``backups``, drop the oldest copies past ``DEFAULT_BACKUPS``, then write
        ``data`` into the file."""
        current = self._home / "default.yaml"
        if current.is_file():
            backups = self._home / "backups"
            backups.mkdir(exist_ok=True)
            shutil.copy2(current, backups / self._backup_name())
            for old in sorted(backups.glob("default-*.yaml"))[: -self.DEFAULT_BACKUPS]:
                old.unlink()
        update_yaml(current, data)

    def _backup_name(self) -> str:
        """The name of a copy of ``default.yaml`` made now: the local date and time, with no character that a file
        name cannot have."""
        return f"default-{datetime.now().astimezone():%Y-%m-%dT%H-%M-%S}.yaml"

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
        # Only an error that the edit adds refuses it: a task gone stale, such as after a change of the rig, must not
        # block every other edit, nor its own fix.
        before = {(found.code, found.loc) for found in self._value.problems(self._config).errors()}
        if found := Problems(p for p in validated.problems(self._config).errors() if (p.code, p.loc) not in before):
            raise RejectedError(str(found), found)
        await asyncio.to_thread(
            atomic_write, self._home / "state.json", validated.model_dump_json(indent=2, exclude_none=True)
        )
        self._value = validated
        self._last_modified = datetime.now(tz=UTC)
        await self._notify(validated)
