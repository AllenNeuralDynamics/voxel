import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict
from ruamel.yaml import YAML

if TYPE_CHECKING:
    from voxel.instrument import Instrument
    from voxel.reporting.errors import ErrorInfo

_yaml = YAML(typ='safe')


class BaseDefinition(BaseModel, ABC):
    """Base class for all definitions that can be persisted.
    It should have a unique identifier (uid) and can be extended by other models.
    """

    uid: str
    description: str | None = None

    model_config = ConfigDict(extra='forbid')

    @abstractmethod
    def validate_definition(self, instrument: 'Instrument') -> Sequence['ErrorInfo']:
        """Validate this definition against the given instrument. Returns sequence of error objects."""
        ...


class Repository[T: BaseDefinition](ABC):
    @abstractmethod
    def list(self) -> list[T]:
        pass

    @abstractmethod
    def save(self, obj: T) -> None:
        pass

    @abstractmethod
    def delete(self, uid: str) -> None:
        pass


class DefinitionStore[T: BaseDefinition]:
    def __init__(self, model: type[T], persistence: Repository[T] | None = None):
        self.model = model
        self._persistence = persistence
        self._items: dict[str, T] = {}
        self._lock = threading.RLock()
        self.reload()

    def reload(self) -> None:
        """Repopulate from the persistence layer (if any)."""
        if not self._persistence:
            return
        with self._lock:
            self._items = {item.uid: item for item in self._persistence.list()}

    def list(self) -> dict[str, T]:
        """Get a snapshot of all definitions in memory."""
        with self._lock:
            return dict(self._items)

    def save(self, obj: T) -> None:
        """Add or update in memory, then persist if configured."""
        with self._lock:
            self._items[obj.uid] = obj
            if self._persistence:
                self._persistence.save(obj)

    def delete(self, uid: str) -> None:
        """Remove from memory, then from persistence if configured."""
        with self._lock:
            self._items.pop(uid, None)
            if self._persistence:
                self._persistence.delete(uid)


class DefinitionsProviderBase[T: BaseDefinition](ABC):
    """Manages an in-memory cache of T plus an optional persistence layer.
    Subclasses must implement `get_build_options()` to expose the schema/options.
    """

    def __init__(
        self,
        instrument: 'Instrument',
        persistence: Repository[T],
    ):
        self._inst = instrument
        self._pers: Repository[T] = persistence
        self._cache: dict[str, T] = {}
        self._lock = threading.Lock()
        if self._pers:
            self.reload()

    def reload(self) -> None:
        """Wipe & refill the in-memory cache from disk (if persistence is set)."""
        if not self._pers:
            return
        with self._lock:
            self._cache = {item.uid: item for item in self._pers.list()}

    def list(self) -> dict[str, T]:
        """Snapshot of all definitions in memory."""
        with self._lock:
            return dict(self._cache)

    def add(self, obj: T) -> Sequence['ErrorInfo']:
        """Validate then add to the cache (and persist if configured).
        Expects T to implement `validate_definition(instrument)`.
        Returns sequence of error objects if validation fails, empty sequence if successful.
        """
        errors = obj.validate_definition(self._inst)
        if not errors:  # No errors means validation passed
            with self._lock:
                self._cache[obj.uid] = obj
                if self._pers:
                    self._pers.save(obj)
        return errors

    def remove(self, uid: str) -> None:
        """Remove from the cache (and disk, if configured)."""
        with self._lock:
            self._cache.pop(uid, None)
            if self._pers:
                self._pers.delete(uid)

    @abstractmethod
    def get_build_options(self) -> BaseModel:
        """Return a BaseModel that exposes the available schema/options to build T."""
