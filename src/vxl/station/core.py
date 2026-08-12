"""Live station authority for instrument ownership and lifecycle."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from vxl_records import SQLiteRecords, VoxelRecords

from vxl.camera import resolve_storage
from vxl.errors import Loaded
from vxl.instrument import Instrument, InstrumentBench, InstrumentConfig, InstrumentInspection
from vxlib import Cell, Computed, Readable, Teardown

from .feed import StationFeed
from .models import DeviceState, SessionInfo, SessionState, StationState, StationStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from vxl.system import StationConfig


def _create_instrument(home: Path, records: VoxelRecords) -> Instrument:
    return Instrument.from_path(home, records=records)


def _describe_error(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


_TEMPLATES_DIR = Path(__file__).parents[1] / "_templates"
log = logging.getLogger(__name__)


type InstrumentFactory = Callable[[Path, VoxelRecords], Instrument]


class InstrumentTemplates:
    """Discover validated instrument configurations from one template directory."""

    def __init__(self, directory: Path | str = _TEMPLATES_DIR) -> None:
        self._directory = Path(directory)

    @property
    def directory(self) -> Path:
        """Directory containing ``*.voxel.yaml`` instrument templates."""
        return self._directory

    def discover(self) -> dict[str, InstrumentConfig]:
        """Return valid templates while logging every invalid configuration."""
        found: dict[str, InstrumentConfig] = {}
        if not self._directory.is_dir():
            return found

        for path in sorted(self._directory.glob("*.voxel.yaml")):
            name = path.name.removesuffix(".voxel.yaml")
            inspected = InstrumentBench.check_config(path)
            if inspected.ok and isinstance(inspected.config, Loaded):
                found[name] = inspected.config.value
                continue
            log.warning(
                "Skipping instrument template '%s': %s",
                path.name,
                "; ".join(violation.msg for violation in inspected.violations),
            )
        return found

    def get(self, name: str) -> InstrumentConfig:
        """Return one valid template or raise when it is unavailable."""
        if (template := self.discover().get(name)) is None:
            raise KeyError(f"No instrument template '{name}'")
        return template


class Station:
    """Own one station configuration, stable feed, and at most one instrument.

    Lifecycle methods are serialized so hardware ownership and the published
    station projection change in one deterministic order. Instrument behavior
    remains on :class:`~vxl.instrument.Instrument`.
    """

    def __init__(
        self,
        config: StationConfig,
        *,
        records: VoxelRecords | None = None,
        instrument_factory: InstrumentFactory | None = None,
        lease_drain_timeout_s: float = 10.0,
    ) -> None:
        if lease_drain_timeout_s <= 0:
            raise ValueError("lease_drain_timeout_s must be positive")
        self._config = config
        self._config.dir.mkdir(parents=True, exist_ok=True)
        self.instruments_dir.mkdir(exist_ok=True)
        self._records = records or SQLiteRecords(
            self._config.dir / "records.sqlite3",
            resolve_root=lambda spec: resolve_storage(spec).target,
        )
        self._instrument_factory = instrument_factory or _create_instrument
        self._instrument: Instrument | None = None
        self._session_info: Computed[SessionInfo] | None = None
        self._session_teardowns: list[Teardown] = []
        self._state = Cell(StationState())
        self._lifecycle_lock = asyncio.Lock()
        self._leases_released = asyncio.Condition(self._lifecycle_lock)
        self._instrument_leases: set[asyncio.Task[object]] = set()
        self._lease_drain_timeout_s = lease_drain_timeout_s
        self._feed = StationFeed(config.info, self._state)

    @property
    def config(self) -> StationConfig:
        """The durable configuration injected into this live station."""
        return self._config

    @property
    def records(self) -> VoxelRecords:
        """The durable record service composed with this station."""
        return self._records

    @property
    def feed(self) -> StationFeed:
        """The stable station feed, independent of instrument lifetime."""
        return self._feed

    @property
    def state(self) -> Readable[StationState]:
        """The current station lifecycle projection as a read-only reactive value."""
        return self._state

    @property
    def instruments_dir(self) -> Path:
        """Root holding the station's ``<name>.voxel`` instrument directories."""
        return self._config.dir / "instruments"

    def discover_instruments(self) -> dict[str, InstrumentInspection]:
        """Inspect every installed instrument without opening hardware."""
        return {
            directory.stem: InstrumentBench.check(directory)
            for directory in sorted(self.instruments_dir.glob("*.voxel"))
            if directory.is_dir()
        }

    async def create_instrument(self, name: str, config: InstrumentConfig) -> InstrumentInspection:
        """Create and inspect one installed instrument from a supplied configuration."""
        async with self._lifecycle_lock:
            self._ensure_file_operation_allowed()
            self._instrument_home(name)
            directory = config.instantiate(name, self.instruments_dir)
            return InstrumentBench.check(directory)

    async def archive_bench(self, instrument_name: str) -> Path:
        """Archive an inactive installed instrument's bench under the next available name."""
        async with self._lifecycle_lock:
            self._ensure_file_operation_allowed()
            state = self._state.value
            if state.session is not None and state.session.info.instrument_name == instrument_name:
                raise RuntimeError(f"'{instrument_name}' is active; close it first")

            directory = self._instrument_home(instrument_name)
            if not directory.is_dir():
                raise FileNotFoundError(f"No instrument '{instrument_name}' under {self.instruments_dir}")
            bench = directory / "bench.json"
            if not bench.exists():
                raise FileNotFoundError(f"No bench.json to archive for '{instrument_name}'")

            archive = directory / "bench.bak.json"
            index = 2
            while archive.exists():
                archive = directory / f"bench.bak.{index}.json"
                index += 1
            bench.rename(archive)
            return archive

    async def open_session(self, instrument_name: str) -> SessionInfo:
        """Open an installed instrument as a new session and publish its complete state.

        A session-opening failure returns the station to ``idle`` only after cleanup
        succeeds. Failed cleanup leaves the station ``faulted``.
        """
        async with self._lifecycle_lock:
            state = self._state.value
            if state.status is StationStatus.CLOSED:
                raise RuntimeError("station is closed")
            if state.status is StationStatus.FAULTED:
                raise RuntimeError("station is faulted; recovery is required before opening a session")
            if self._instrument is not None:
                active_name = state.session.info.instrument_name if state.session is not None else "unknown"
                raise RuntimeError(f"'{active_name}' is active; close it first")
            if state.status is not StationStatus.IDLE:
                raise RuntimeError(f"station cannot open a session while {state.status}")

            instrument_home = self._instrument_home(instrument_name)
            if not instrument_home.is_dir():
                raise FileNotFoundError(f"No instrument '{instrument_name}' under {self.instruments_dir}")

            await self._state.set(StationState(status=StationStatus.OPENING))
            instrument: Instrument | None = None
            try:
                instrument = self._instrument_factory(instrument_home, self._records)
                await instrument.open()
                self._instrument = instrument
                session_id = uuid4()
                self._session_info = Computed(
                    instrument.mode,
                    instrument.active_profile_id,
                    instrument.preview_revision,
                    instrument.fov,
                    instrument.routing_targets,
                    fn=lambda: SessionInfo(
                        id=session_id,
                        instrument_name=instrument_name,
                        mode=instrument.mode.value,
                        active_profile_id=instrument.active_profile_id.value,
                        preview_revision=instrument.preview_revision.value,
                        fov=instrument.fov.cache,
                        routing_targets=instrument.routing_targets.value,
                    ),
                )
                self._session_teardowns.append(self._session_info.subscribe(self._refresh_session_state))
                self._session_teardowns.append(instrument.state.subscribe(self._refresh_session_state))
                self._session_teardowns.append(instrument.task_tiles.subscribe(self._refresh_session_state))
                self._session_teardowns.append(instrument.acquisition.subscribe(self._refresh_session_state))
                self._session_teardowns.append(instrument.default.subscribe(self._refresh_session_state))
                self._session_teardowns.append(instrument.device_props_updates.subscribe(self._refresh_session_state))
                self._session_teardowns.append(instrument.preview.subscribe(self._feed.publish_preview))
                session_state = self._build_session_state(instrument)
            except BaseException as launch_error:
                await self._teardown_failed_launch(instrument, launch_error)
                raise

            await self._state.set(StationState(status=StationStatus.ACTIVE, session=session_state))
            return session_state.info

    @asynccontextmanager
    async def instrument(self, session_id: UUID) -> AsyncIterator[Instrument]:
        """Lease the active instrument for the duration of one scoped operation."""
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("instrument access requires an asyncio task")

        async with self._leases_released:
            state = self._state.value
            if state.status is not StationStatus.ACTIVE or state.session is None or self._instrument is None:
                raise RuntimeError("station has no active instrument session")
            if state.session.info.id != session_id:
                raise RuntimeError(f"instrument session '{session_id}' is not active")
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
        """Close any active session and permanently stop this station's feed."""
        async with self._lifecycle_lock:
            if self._state.value.status is StationStatus.CLOSED:
                await self._feed.close()
                return
            await self._close_session_locked()
            await self._state.set(StationState(status=StationStatus.CLOSED))
            await self._feed.close()

    async def _close_session_locked(self, expected_session_id: UUID | None = None) -> None:
        state = self._state.value
        if state.status is StationStatus.FAULTED:
            raise RuntimeError("station is faulted; recovery is required before closing normally")
        if self._instrument is None:
            if expected_session_id is not None:
                raise RuntimeError("station has no active instrument session")
            return

        session_state = state.session
        if session_state is None:
            raise RuntimeError("station owns an instrument without an active session")
        if state.status is not StationStatus.ACTIVE:
            raise RuntimeError(f"station cannot close a session while {state.status}")
        if expected_session_id is not None and session_state.info.id != expected_session_id:
            raise RuntimeError(f"instrument session '{expected_session_id}' is not active")

        task = asyncio.current_task()
        if task is not None and task in self._instrument_leases:
            raise RuntimeError("cannot close an instrument session from a task holding its lease")

        try:
            await self._state.set(StationState(status=StationStatus.CLOSING, session=session_state))
            async with asyncio.timeout(self._lease_drain_timeout_s):
                await self._leases_released.wait_for(lambda: not self._instrument_leases)
        except TimeoutError as error:
            current_session = self._state.value.session or session_state
            await self._state.set(StationState(status=StationStatus.ACTIVE, session=current_session))
            msg = f"instrument session still has active leases after {self._lease_drain_timeout_s:g} seconds"
            raise TimeoutError(msg) from error
        except BaseException:
            current_session = self._state.value.session or session_state
            await self._state.set(StationState(status=StationStatus.ACTIVE, session=current_session))
            raise

        instrument = self._instrument
        for teardown in self._session_teardowns:
            teardown()
        self._session_teardowns = []
        self._feed.clear_preview()
        if self._session_info is not None:
            self._session_info.close()
        self._session_info = None
        try:
            await instrument.close()
        except BaseException as error:
            current_session = self._state.value.session or session_state
            await self._state.set(
                StationState(
                    status=StationStatus.FAULTED,
                    session=current_session,
                    error=_describe_error(error),
                )
            )
            raise

        self._instrument = None
        await self._state.set(StationState())

    async def _refresh_session_state(self, _value: object) -> None:
        instrument = self._instrument
        if instrument is None or self._session_info is None:
            return
        current = self._state.value
        if current.status not in {StationStatus.ACTIVE, StationStatus.CLOSING}:
            return
        await self._state.set(
            StationState(
                status=current.status,
                session=self._build_session_state(instrument),
                error=current.error,
            )
        )

    async def _teardown_failed_launch(self, instrument: Instrument | None, launch_error: BaseException) -> None:
        for teardown in self._session_teardowns:
            teardown()
        self._session_teardowns = []
        self._feed.clear_preview()
        if self._session_info is not None:
            self._session_info.close()
        self._session_info = None

        if instrument is None:
            self._instrument = None
            await self._state.set(StationState(status=StationStatus.IDLE, error=_describe_error(launch_error)))
            return

        try:
            await instrument.close()
        except BaseException as cleanup_error:
            self._instrument = instrument
            await self._state.set(
                StationState(
                    status=StationStatus.FAULTED,
                    error=(
                        f"session open failed ({_describe_error(launch_error)}); "
                        f"cleanup failed ({_describe_error(cleanup_error)})"
                    ),
                )
            )
            raise cleanup_error from launch_error

        self._instrument = None
        await self._state.set(StationState(status=StationStatus.IDLE, error=_describe_error(launch_error)))

    def _instrument_home(self, instrument_name: str) -> Path:
        if not instrument_name or Path(instrument_name).name != instrument_name or instrument_name in {".", ".."}:
            raise ValueError("instrument_name must be a single non-empty path component")
        return self.instruments_dir / f"{instrument_name}.voxel"

    def _ensure_file_operation_allowed(self) -> None:
        status = self._state.value.status
        if status is StationStatus.CLOSED:
            raise RuntimeError("station is closed")
        if status is StationStatus.FAULTED:
            raise RuntimeError("station is faulted; recovery is required before modifying instruments")

    def _build_session_state(self, instrument: Instrument) -> SessionState:
        if self._session_info is None:
            raise RuntimeError("station instrument has no attached session")
        device_props = instrument.device_props
        return SessionState(
            info=self._session_info.value,
            bench=instrument.state.value,
            task_tiles=instrument.task_tiles.value,
            devices={
                device_id: DeviceState(
                    interface=interface,
                    props=dict(device_props.get(device_id, {})),
                )
                for device_id, interface in instrument.device_interfaces.items()
            },
            acquisition=instrument.acquisition.value,
            defaults=instrument.default.value,
            hardware=instrument.hardware_config,
        )


__all__ = ["InstrumentTemplates", "Station"]
