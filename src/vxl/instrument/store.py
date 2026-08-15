import asyncio
import datetime
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, ValidationError, model_validator

from vxlib import Cell, Readable, Subscribable, atomic_write, load_yaml, save_yaml

from .config import InstrumentConfig, InstrumentDefaults, InstrumentPreset, InstrumentState
from .errors import OperationRejectedError, StartupError, Violation

PROMOTABLE_FIELDS = frozenset(InstrumentDefaults.model_fields)
"""Baseline fields that can move between the live state and persisted instrument defaults."""


class Loaded[T: BaseModel](BaseModel, frozen=True):
    """A persisted model that was found, read, and fully validated."""

    status: Literal["loaded"] = "loaded"
    value: T


class Missing(BaseModel, frozen=True):
    """A persisted model whose file was not found."""

    status: Literal["missing"] = "missing"


class Invalid[T: BaseModel](BaseModel, frozen=True):
    """A persisted model that failed structural or semantic validation."""

    status: Literal["invalid"] = "invalid"
    value: T | None = None


type Inspected[T: BaseModel] = Annotated[Loaded[T] | Missing | Invalid[T], Field(discriminator="status")]


def _load_model[T: BaseModel](path: Path, model: type[T], source: str) -> tuple[Inspected[T], tuple[Violation, ...]]:
    """Load one persisted model, returning structured violations instead of raising."""
    try:
        return Loaded(value=load_yaml(path, model)), ()
    except FileNotFoundError:
        return Missing(), ()
    except ValidationError as exc:
        return Invalid[T](), tuple(
            Violation(
                code=f"{source}.{error['type']}",
                msg=error["msg"],
                loc=(source, *error["loc"]),
            )
            for error in exc.errors()
        )
    except Exception as exc:
        return Invalid[T](), (Violation(code=f"{source}.load", msg=str(exc), loc=(source,)),)


@dataclass(frozen=True)
class InstrumentSetup:
    """A coherent, statically validated snapshot used to construct a store."""

    home: Path
    config: InstrumentConfig
    state: InstrumentState


class InstrumentInspection(BaseModel, frozen=True):
    """Fault-tolerant static inspection of an instrument's persisted configuration and state."""

    config: Inspected[InstrumentConfig]
    state: Inspected[InstrumentState] = Field(default_factory=Missing)
    violations: tuple[Violation, ...] = ()

    @model_validator(mode="after")
    def check_blocking_status_violations(self) -> Self:
        """Ensure every unusable artifact status has a corresponding structured violation."""
        sources = {violation.loc[0] for violation in self.violations if violation.loc}
        if isinstance(self.config, (Missing, Invalid)) and "config" not in sources:
            raise ValueError("missing or invalid config must include a config violation")
        if isinstance(self.state, Invalid) and "state" not in sources:
            raise ValueError("invalid state must include a state violation")
        return self

    @property
    def ok(self) -> bool:
        """Whether the inspected artifacts can be loaded as an instrument store."""
        return isinstance(self.config, Loaded) and not self.violations


class InstrumentStore(Subscribable[InstrumentState]):
    """Validating persistence for one :class:`InstrumentState`."""

    @staticmethod
    def instantiate(config: InstrumentConfig, name: str, into: Path | str) -> Path:
        """Create ``<into>/<name>.voxel`` and persist its initial configuration."""
        directory = Path(into) / f"{name}.voxel"
        if directory.exists():
            raise FileExistsError(f"Instrument '{name}' already exists at {directory}")
        directory.mkdir(parents=True)
        save_yaml(directory / "config.yaml", config)
        return directory

    @staticmethod
    def load_config(path: Path | str) -> InstrumentInspection:
        """Load and semantically inspect one instrument configuration without raising."""
        path = Path(path)
        config, violations = _load_model(path, InstrumentConfig, "config")
        if isinstance(config, Missing):
            violations = (
                Violation(
                    code="config.missing",
                    msg=f"No InstrumentConfig found at {path}",
                    loc=("config",),
                ),
            )
        elif isinstance(config, Loaded):
            semantic_violations = tuple(config.value.semantic_violations())
            if semantic_violations:
                config = Invalid[InstrumentConfig](value=config.value)
                violations = (*violations, *semantic_violations)
        return InstrumentInspection(config=config, violations=violations)

    @classmethod
    def load(cls, home: Path | str) -> Self:
        """Load valid instrument state, raising one structured startup error on failure."""
        home = Path(home)
        inspection = cls.check(home)
        if inspection.violations:
            raise StartupError(list(inspection.violations))
        match inspection.config, inspection.state:
            case Loaded(value=config), Loaded(value=state):
                pass
            case Loaded(value=config), Missing():
                state = InstrumentState(**config.default.model_dump())
            case _:
                raise RuntimeError("Invalid instrument inspection without violations")
        return cls(InstrumentSetup(home=home, config=config, state=state))

    @classmethod
    def check(cls, home: Path | str) -> InstrumentInspection:
        """Inspect an instrument directory without opening hardware or raising for invalid persisted state."""
        home = Path(home)
        config_inspection = cls.load_config(home / "config.yaml")
        config = config_inspection.config
        state, state_violations = _load_model(home / "state.json", InstrumentState, "state")
        violations = [*config_inspection.violations, *state_violations]
        config_value = config.value if isinstance(config, (Loaded, Invalid)) else None
        if config_value is not None and isinstance(state, Loaded):
            semantic_violations = tuple(state.value.semantic_violations(config_value.hal))
            if semantic_violations:
                state = Invalid[InstrumentState](value=state.value)
                violations.extend(semantic_violations)
        return InstrumentInspection(
            config=config,
            state=state,
            violations=tuple(violations),
        )

    def __init__(self, setup: InstrumentSetup) -> None:
        super().__init__()
        self._home = setup.home
        self._config = setup.config
        self._path = setup.home / "state.json"
        self._hal = setup.config.hal
        self._value = setup.state
        self._default = Cell(setup.config.default)
        self._lock = asyncio.Lock()

    @property
    def home(self) -> Path:
        """The instrument's on-disk home."""
        return self._home

    @property
    def config(self) -> InstrumentConfig:
        """The statically validated instrument configuration."""
        return self._config

    @property
    def default(self) -> Readable[InstrumentDefaults]:
        """The persisted instrument defaults as a reactive read-only view."""
        return self._default

    @property
    def value(self) -> InstrumentState:
        """The current committed state — frozen, safe to hand out without copying."""
        return self._value

    async def _save(self, state: InstrumentState) -> None:
        """Persist `state` durably off the event loop. Writes exactly `state`."""
        await asyncio.to_thread(atomic_write, self._path, state.model_dump_json(indent=2, exclude_none=True))

    async def set(self, candidate: InstrumentState) -> None:
        """Validate, persist, and adopt `candidate`, notifying subscribers with the new state.

        Re-runs the model validators (via a ``model_dump`` round-trip — ``model_copy`` skips them) and the
        instrument's HAL compatibility check. Raises :class:`OperationRejectedError` and changes nothing if either
        rejects it. A candidate identical to the current state (a no-op edit) is dropped before stamping: no save,
        no notify (`last_modified` is excluded from the comparison so an unchanged edit doesn't churn).
        """
        async with self._lock:
            await self._commit(candidate)

    async def update(self, **updates: Any) -> None:
        """Atomically read the current state, patch top-level fields, then validate and persist.

        The read-modify-write runs under the store lock, so concurrent ``update``/``set`` calls cannot
        interleave into a lost update or a double notify.
        """
        async with self._lock:
            await self._commit(self._value.model_copy(update=updates))

    async def save_as_default(self, include: Collection[str] = PROMOTABLE_FIELDS) -> None:
        """Persist selected fields from the live state into the instrument defaults."""
        fields = set(include)
        if unknown := fields - PROMOTABLE_FIELDS:
            raise OperationRejectedError(f"Cannot promote non-default fields: {sorted(unknown)}")

        async with self._lock:
            new_default = self._default.value.model_copy(
                update={field: getattr(self._value, field) for field in fields}
            )
            new_config = self._config.model_copy(update={"default": new_default})
            await asyncio.to_thread(save_yaml, self._home / "config.yaml", new_config)
            self._config = new_config
            await self._default.set(new_default)

    async def restore_default(self, include: Collection[str] = PROMOTABLE_FIELDS) -> None:
        """Restore selected live-state fields from the persisted instrument defaults."""
        fields = set(include)
        if unknown := fields - PROMOTABLE_FIELDS:
            raise OperationRejectedError(f"Cannot restore non-default fields: {sorted(unknown)}")

        async with self._lock:
            default = self._default.value
            await self._commit(self._value.model_copy(update={field: getattr(default, field) for field in fields}))

    async def apply_preset(self, preset: InstrumentPreset) -> None:
        """Atomically replace reusable state fields while preserving compatible specimen metadata."""
        async with self._lock:
            metadata = self._value.metadata if preset.metadata_cls == self._value.metadata_cls else {}
            candidate = InstrumentState.model_validate(
                {
                    **preset.model_dump(),
                    "metadata": metadata,
                    "last_modified": self._value.last_modified,
                }
            )
            await self._commit(candidate)

    async def _commit(self, candidate: InstrumentState) -> None:
        """Validate, drop no-ops, check HAL compatibility, persist, adopt, and notify."""
        try:
            validated = InstrumentState.model_validate(candidate.model_dump())
        except ValidationError as e:
            raise OperationRejectedError("; ".join(err["msg"] for err in e.errors())) from e
        if validated.model_copy(update={"last_modified": self._value.last_modified}) == self._value:
            return  # no-op edit (ignoring the timestamp): no save, no notify
        if violations := validated.semantic_violations(self._hal):
            raise OperationRejectedError("; ".join(violation.msg for violation in violations))
        stamped = validated.model_copy(update={"last_modified": datetime.datetime.now(tz=datetime.UTC)})
        await self._save(stamped)
        self._value = stamped
        await self._notify(stamped)
