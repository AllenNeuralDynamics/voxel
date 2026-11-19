"""Live station authority for instrument ownership and lifecycle."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, field_validator, model_validator
from pydantic_settings import BaseSettings, EnvSettingsSource, PydanticBaseSettingsSource
from vxl_records import SQLiteRecords, VoxelRecords
from vxlib.reactivity import Cell, Emitter, Readable
from vxlib.schema import FrozenModel, check_identifier

from vxl import system
from vxl._utils.files import save_yaml
from vxl.core.errors import BusyError, RejectedError, StationNotConfiguredError
from vxl.core.instrument.base import Instrument, InstrumentView
from vxl.core.instrument.folder import InstrumentFolder
from vxl.live import LiveSourceEmission
from vxl.metadata import BASE_METADATA_SCHEMA, resolve_metadata_class
from vxl.system import System

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping
    from pathlib import Path

    from vxlib.lifecycle import Teardown
    from vxlib.reactivity import Subscribable


type AnyInstrument = Instrument[Any, Any]


class StationInfo(BaseModel):
    """Stable public identity of a Voxel control station."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str


class StationStatus(StrEnum):
    """Lifecycle status of the station's active session."""

    IDLE = "idle"
    OPENING = "opening"
    ACTIVE = "active"
    CLOSING = "closing"
    FAULTED = "faulted"
    CLOSED = "closed"


class SessionInfo(FrozenModel):
    """Stable identity of one opened instrument session."""

    id: UUID
    instrument_name: str = Field(min_length=1)


class SessionView(FrozenModel):
    """Complete bounded view belonging to one opened instrument session."""

    info: SessionInfo
    instrument: SerializeAsAny[InstrumentView]


class StationView(FrozenModel):
    """The live station as a screen sees it: its phase, its open session, and its last error."""

    status: StationStatus = StationStatus.IDLE
    session: SessionView | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _validate_session_lifecycle(self) -> Self:
        if self.status in {StationStatus.ACTIVE, StationStatus.CLOSING} and self.session is None:
            raise ValueError(f"{self.status} station state requires a session")
        empty_statuses = {StationStatus.IDLE, StationStatus.OPENING, StationStatus.CLOSED}
        if self.status in empty_statuses and self.session is not None:
            raise ValueError(f"{self.status} station state cannot contain a session")
        return self


def _describe_error(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


class _SystemFieldsEnvSource(EnvSettingsSource):
    """Restrict station env overrides to machine policy; identity remains file-backed."""

    def __call__(self) -> dict[str, object]:
        return {key: value for key, value in super().__call__().items() if key in System.model_fields}


class StationConfig(System):
    """Persisted control-station identity plus the complete local :class:`System` config.

    Unlike :class:`System`, this configuration never falls back to ``system.yaml``. Control
    entrypoints use :meth:`load` so a missing station is reported clearly; remote nodes continue
    to construct ``System`` and therefore need no station identity. The live station authority is
    intentionally a separate concept from this settings model.
    """

    schema_version: Literal[1] = 1
    id: UUID
    name: str = Field(min_length=1)
    metadata_schemas: dict[str, str] = Field(
        default_factory=dict, description="menu name -> dotted path of an ExperimentMetadata subclass"
    )

    @field_validator("metadata_schemas")
    @classmethod
    def _check_metadata_schemas(cls, value: dict[str, str]) -> dict[str, str]:
        for name, target in value.items():
            try:
                resolve_metadata_class(target)
            except (ImportError, AttributeError, TypeError, ValueError) as error:
                raise ValueError(f"'{name}': {error}") from error
        return value

    def metadata_menu(self) -> dict[str, str]:
        """The metadata forms that this station offers: the base form, then those of ``metadata_schemas``."""
        return {"Base": BASE_METADATA_SCHEMA, **self.metadata_schemas}

    @classmethod
    def station_dir(cls) -> Path:
        """The station's own folder, ``new`` in the Voxel home: its config, instruments and records. The machine's
        files (process registry, ``.env``, data roots) stay in the Voxel home."""
        return system.voxel_home() / "new"

    @classmethod
    def config_path(cls) -> Path:
        """Return the required control-station configuration path."""
        return cls.station_dir() / "station.yaml"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Read station YAML only; ``system.yaml`` is not a second configuration authority."""
        del env_settings, dotenv_settings, file_secret_settings
        return (
            init_settings,
            _SystemFieldsEnvSource(settings_cls),
            system.yaml_source(settings_cls, cls.config_path()),
        )

    @classmethod
    def load(cls) -> Self:
        """Load the control station or explain how to initialize one."""
        path = cls.config_path()
        if not path.is_file():
            raise StationNotConfiguredError(
                f"No control station configured at {path}. Initialize one with `vxl init --name <name>`."
            )
        return cls()  # pyright: ignore[reportCallIssue] -- required fields come from the checked YAML source

    @classmethod
    def initialize(cls, name: str, *, station_id: UUID | None = None) -> Self:
        """Create ``station.yaml`` from the effective System config, refusing to overwrite it."""
        path = cls.config_path()
        if path.exists():
            raise FileExistsError(f"A control station is already configured at {path}")

        machine = System()
        station_config = cls(
            schema_version=1,
            id=station_id or uuid4(),
            name=name,
            store=machine.store,
            scratch=machine.scratch,
            max_ram_fraction=machine.max_ram_fraction,
            remotes=machine.remotes,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(path, station_config)
        return station_config

    @property
    def info(self) -> StationInfo:
        """Return the bounded station identity safe to expose to clients."""
        return StationInfo(id=self.id, name=self.name)


class Station:
    """Own one station configuration and at most one instrument.

    Lifecycle methods are serialized so hardware ownership and the published
    station projection change in one deterministic order. Instrument behavior
    remains on the instrument. The ``target`` of an instrument's ``rig.yaml`` names the class that runs it, and that
    class names the classes of its files.
    """

    def __init__(
        self,
        config: StationConfig,
        *,
        records: VoxelRecords | None = None,
        lease_drain_timeout_s: float = 10.0,
    ) -> None:
        if lease_drain_timeout_s <= 0:
            raise ValueError("lease_drain_timeout_s must be positive")
        self._config = config
        self.instruments_dir.mkdir(parents=True, exist_ok=True)
        self._records = records or SQLiteRecords(
            self._config.station_dir() / "records.sqlite3",
            resolve_root=lambda spec: self._config.resolve_storage(spec).target,
        )
        self._instrument: AnyInstrument | None = None
        self._session_info: SessionInfo | None = None
        self._session_teardowns: list[Teardown] = []
        self._view = Cell(StationView())
        self._live = Emitter[LiveSourceEmission]()
        self._lifecycle_lock = asyncio.Lock()
        self._leases_released = asyncio.Condition(self._lifecycle_lock)
        self._instrument_leases: set[asyncio.Task[object]] = set()
        self._lease_drain_timeout_s = lease_drain_timeout_s

    @property
    def config(self) -> StationConfig:
        """The durable configuration injected into this live station."""
        return self._config

    @property
    def records(self) -> VoxelRecords:
        """The durable record service composed with this station."""
        return self._records

    @property
    def view(self) -> Readable[StationView]:
        """The live station as a screen sees it."""
        return self._view

    @property
    def live(self) -> Subscribable[LiveSourceEmission]:
        """Each live frame of the open instrument, unopened, as :attr:`Instrument.live` gives it."""
        return self._live

    @property
    def instruments_dir(self) -> Path:
        """Root holding the station's ``<name>.voxel`` instrument directories."""
        return self._config.station_dir() / "instruments"

    def discover_instruments(self) -> dict[str, InstrumentFolder]:
        """Inspect every installed instrument without opening hardware."""
        return {
            directory.stem: InstrumentFolder.read(directory)
            for directory in sorted(self.instruments_dir.glob("*.voxel"))
            if directory.is_dir()
        }

    async def create_instrument(self, name: str, template: Mapping[str, Any]) -> InstrumentFolder:
        """Create and inspect one installed instrument from a template: a ``rig`` and a ``default``."""
        async with self._lifecycle_lock:
            self._ensure_file_operation_allowed()
            self._instrument_home(name)
            return InstrumentFolder.create(template, name, self.instruments_dir)

    async def archive_state(self, instrument_name: str) -> Path:
        """Archive an inactive installed instrument's state under the next available name."""
        async with self._lifecycle_lock:
            self._ensure_file_operation_allowed()
            view = self._view.value
            if view.session is not None and view.session.info.instrument_name == instrument_name:
                raise BusyError(f"'{instrument_name}' is active; close it first")

            directory = self._instrument_home(instrument_name)
            if not directory.is_dir():
                raise RejectedError(f"No instrument '{instrument_name}' under {self.instruments_dir}")
            state_path = directory / "state.json"
            if not state_path.exists():
                raise RejectedError(f"No state.json to archive for '{instrument_name}'")

            archive = directory / "state.bak.json"
            index = 2
            while archive.exists():
                archive = directory / f"state.bak.{index}.json"
                index += 1
            state_path.rename(archive)
            return archive

    async def open_session(self, instrument_name: str) -> SessionInfo:
        """Open an installed instrument as a new session and publish its complete state.

        A session-opening failure returns the station to ``idle`` only after cleanup
        succeeds. Failed cleanup leaves the station ``faulted``.
        """
        async with self._lifecycle_lock:
            view = self._view.value
            if view.status is StationStatus.CLOSED:
                raise BusyError("station is closed")
            if view.status is StationStatus.FAULTED:
                raise BusyError("station is faulted; recovery is required before opening a session")
            if self._instrument is not None:
                active_name = view.session.info.instrument_name if view.session is not None else "unknown"
                raise BusyError(f"'{active_name}' is active; close it first")
            if view.status is not StationStatus.IDLE:
                raise BusyError(f"station cannot open a session while {view.status}")

            instrument_home = self._instrument_home(instrument_name)
            if not instrument_home.is_dir():
                raise RejectedError(f"No instrument '{instrument_name}' under {self.instruments_dir}")

            await self._view.set(StationView(status=StationStatus.OPENING))
            instrument: AnyInstrument | None = None
            try:
                folder = InstrumentFolder.read(instrument_home)
                instrument = folder.instrument(records=self._records, system=self._config)
                await instrument.open()
                self._instrument = instrument
                session_id = uuid4()
                self._session_info = SessionInfo(
                    id=session_id,
                    instrument_name=instrument_name,
                )
                self._session_teardowns.append(instrument.view.subscribe(self._refresh_session_view))
                self._session_teardowns.append(instrument.live.subscribe(self._live.emit))
                session_view = self._build_session_view(instrument)
            except BaseException as launch_error:
                await self._teardown_failed_launch(instrument, launch_error)
                raise

            await self._view.set(StationView(status=StationStatus.ACTIVE, session=session_view))
            return session_view.info

    @asynccontextmanager
    async def instrument(self, session_id: UUID) -> AsyncGenerator[AnyInstrument]:
        """Lease the active instrument for the duration of one scoped operation."""
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("instrument access requires an asyncio task")

        async with self._leases_released:
            view = self._view.value
            if view.status is not StationStatus.ACTIVE or view.session is None or self._instrument is None:
                raise BusyError("station has no active instrument session")
            if view.session.info.id != session_id:
                raise BusyError(f"instrument session '{session_id}' is not active")
            if task in self._instrument_leases:
                raise RuntimeError("nested instrument access from the same task is not supported")
            instrument = self._instrument
            self._instrument_leases.add(task)

        try:
            yield instrument
        finally:
            async with self._leases_released:
                self._instrument_leases.discard(task)
                self._leases_released.notify_all()

    async def close_session(self, session_id: UUID) -> None:
        """Close the expected active session after its instrument leases drain."""
        async with self._lifecycle_lock:
            await self._close_session_locked(session_id)

    async def close(self) -> None:
        """Close any active session and mark the station closed for good."""
        async with self._lifecycle_lock:
            if self._view.value.status is StationStatus.CLOSED:
                return
            await self._close_session_locked()
            await self._view.set(StationView(status=StationStatus.CLOSED))

    async def _close_session_locked(self, expected_session_id: UUID | None = None) -> None:
        view = self._view.value
        if view.status is StationStatus.FAULTED:
            raise BusyError("station is faulted; recovery is required before closing normally")
        if self._instrument is None:
            if expected_session_id is not None:
                raise BusyError("station has no active instrument session")
            return

        session_view = view.session
        if session_view is None:
            raise RuntimeError("station owns an instrument without an active session")
        if view.status is not StationStatus.ACTIVE:
            raise BusyError(f"station cannot close a session while {view.status}")
        if expected_session_id is not None and session_view.info.id != expected_session_id:
            raise BusyError(f"instrument session '{expected_session_id}' is not active")

        task = asyncio.current_task()
        if task is not None and task in self._instrument_leases:
            raise RuntimeError("cannot close an instrument session from a task holding its lease")

        try:
            await self._view.set(StationView(status=StationStatus.CLOSING, session=session_view))
            async with asyncio.timeout(self._lease_drain_timeout_s):
                await self._leases_released.wait_for(lambda: not self._instrument_leases)
        except TimeoutError as error:
            current_session = self._view.value.session or session_view
            await self._view.set(StationView(status=StationStatus.ACTIVE, session=current_session))
            msg = f"instrument session still has active leases after {self._lease_drain_timeout_s:g} seconds"
            raise BusyError(msg) from error
        except BaseException:
            current_session = self._view.value.session or session_view
            await self._view.set(StationView(status=StationStatus.ACTIVE, session=current_session))
            raise

        instrument = self._instrument
        for teardown in self._session_teardowns:
            teardown()
        self._session_teardowns = []
        self._session_info = None
        try:
            await instrument.close()
        except BaseException as error:
            current_session = self._view.value.session or session_view
            await self._view.set(
                StationView(
                    status=StationStatus.FAULTED,
                    session=current_session,
                    error=_describe_error(error),
                )
            )
            raise

        self._instrument = None
        await self._view.set(StationView())

    async def _refresh_session_view(self, _value: object) -> None:
        instrument = self._instrument
        if instrument is None or self._session_info is None:
            return
        current = self._view.value
        if current.status not in {StationStatus.ACTIVE, StationStatus.CLOSING}:
            return
        await self._view.set(
            StationView(
                status=current.status,
                session=self._build_session_view(instrument),
                error=current.error,
            )
        )

    async def _teardown_failed_launch(self, instrument: AnyInstrument | None, launch_error: BaseException) -> None:
        for teardown in self._session_teardowns:
            teardown()
        self._session_teardowns = []
        self._session_info = None

        if instrument is None:
            self._instrument = None
            await self._view.set(StationView(status=StationStatus.IDLE, error=_describe_error(launch_error)))
            return

        try:
            await instrument.close()
        except BaseException as cleanup_error:
            self._instrument = instrument
            await self._view.set(
                StationView(
                    status=StationStatus.FAULTED,
                    error=(
                        f"session open failed ({_describe_error(launch_error)}); "
                        f"cleanup failed ({_describe_error(cleanup_error)})"
                    ),
                )
            )
            raise cleanup_error from launch_error

        self._instrument = None
        await self._view.set(StationView(status=StationStatus.IDLE, error=_describe_error(launch_error)))

    def _instrument_home(self, instrument_name: str) -> Path:
        check_identifier(instrument_name, "Instrument name")
        return self.instruments_dir / f"{instrument_name}.voxel"

    def _ensure_file_operation_allowed(self) -> None:
        status = self._view.value.status
        if status is StationStatus.CLOSED:
            raise BusyError("station is closed")
        if status is StationStatus.FAULTED:
            raise BusyError("station is faulted; recovery is required before modifying instruments")

    def _build_session_view(self, instrument: AnyInstrument) -> SessionView:
        if self._session_info is None:
            raise RuntimeError("station instrument has no attached session")
        return SessionView(info=self._session_info, instrument=instrument.view.value)


__all__ = [
    "SessionInfo",
    "SessionView",
    "Station",
    "StationConfig",
    "StationInfo",
    "StationStatus",
    "StationView",
]
