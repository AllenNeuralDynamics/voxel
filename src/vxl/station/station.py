"""Live station authority for instrument ownership and lifecycle."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self
from uuid import UUID, uuid4

from pydantic import Field, SerializeAsAny, model_validator
from vxlib.reactivity import Cell, Emitter, Readable
from vxlib.schema import FrozenModel, check_identifier

from vxl.instrument.base import Instrument, InstrumentView
from vxl.instrument.folder import InstrumentFolder
from vxl.live import LiveSourceEmission
from vxl.records import Records
from vxl.station.errors import BusyError, NotFoundError, RejectedError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping
    from pathlib import Path

    from vxlib.lifecycle import Teardown
    from vxlib.reactivity import Subscribable

    from vxl.station.config import StationConfig


type AnyInstrument = Instrument[Any, Any]


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
        records: Records | None = None,
        lease_drain_timeout_s: float = 10.0,
    ) -> None:
        if lease_drain_timeout_s <= 0:
            raise ValueError("lease_drain_timeout_s must be positive")
        self._config = config
        self.instruments_dir.mkdir(parents=True, exist_ok=True)
        self._records = records or Records(
            self._config.station_dir() / "records.sqlite3",
            resolve_root=lambda spec: self._config.resolve_storage(spec).target,
        )
        self._log_capture: AsyncExitStack | None = None
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
    def records(self) -> Records:
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

    def inspect(self, name: str) -> InstrumentFolder:
        """Inspect 1 installed instrument without opening hardware. Raise :class:`NotFoundError` when no folder has
        that name."""
        home = self._instrument_home(name)
        if not home.is_dir():
            raise NotFoundError(f"No instrument '{name}' under {self.instruments_dir}")
        return InstrumentFolder.read(home)

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
                raise NotFoundError(f"No instrument '{instrument_name}' under {self.instruments_dir}")
            state_path = directory / "state.json"
            if not state_path.exists():
                raise NotFoundError(f"No state.json to archive for '{instrument_name}'")

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
                raise NotFoundError(f"No instrument '{instrument_name}' under {self.instruments_dir}")

            await self._view.set(StationView(status=StationStatus.OPENING))
            instrument: AnyInstrument | None = None
            try:
                folder = self.inspect(instrument_name)
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

    async def open(self) -> list[UUID]:
        """Start keeping every log line of the session in the records, and end each acquisition that an earlier run
        left open as interrupted. Give back their ids. Calling it again only ends open acquisitions again."""
        async with self._lifecycle_lock:
            if self._log_capture is None:
                stack = AsyncExitStack()
                await stack.enter_async_context(self._records.logs.capture())
                self._log_capture = stack
        return await self._records.acquisitions.interrupt_open()

    async def close(self) -> None:
        """Close any active session, stop keeping log lines, and mark the station closed for good."""
        async with self._lifecycle_lock:
            if self._view.value.status is StationStatus.CLOSED:
                return
            try:
                await self._close_session_locked()
            finally:
                if self._log_capture is not None:
                    await self._log_capture.aclose()
                    self._log_capture = None
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
        try:
            check_identifier(instrument_name, "Instrument name")
        except ValueError as error:
            raise RejectedError(str(error)) from error
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
    "StationStatus",
    "StationView",
]
