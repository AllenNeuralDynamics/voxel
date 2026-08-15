import asyncio
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from vxl_records import VoxelRecords

from rigup import DeviceInterface, DeviceProps
from vxl import system as system_module
from vxl.instrument import (
    AcquisitionMode,
    ActiveAcquisitionState,
    Instrument,
    InstrumentConfig,
    InstrumentState,
)
from vxl.instrument.models import TaskTile
from vxl.preview import PreviewLayer, PreviewSourceEmission, VoxelPreviewPacket
from vxl.station import Station, StationStatus
from vxl.system import StationConfig
from vxlib import Cell, Emitter, ReactiveQuery, load_yaml

TEMPLATE = Path(__file__).parents[1] / "src/vxl/station/templates/builtins/simulated-local.voxel.yaml"
INSTRUMENT_CONFIG = load_yaml(TEMPLATE, InstrumentConfig)
STATE = InstrumentState(**INSTRUMENT_CONFIG.default.model_dump())


class FakeInstrument:
    def __init__(
        self,
        events: list[str],
        *,
        open_error: Exception | None = None,
        close_error: Exception | None = None,
        open_started: asyncio.Event | None = None,
        open_release: asyncio.Event | None = None,
    ) -> None:
        self.events = events
        self.open_error = open_error
        self.close_error = close_error
        self.open_started = open_started
        self.open_release = open_release
        self.state = Cell(STATE)
        self.default = Cell(INSTRUMENT_CONFIG.default)
        self.mode = Cell(AcquisitionMode.IDLE)
        self.acquisition = Cell[ActiveAcquisitionState | None](None)
        self.active_profile_id = Cell(next(iter(STATE.imaging.profiles)))
        self.routing_targets = Cell[dict[str, str]]({})
        self.device_interfaces: dict[str, DeviceInterface] = {}
        self.device_props: dict[str, DeviceProps] = {}
        self.remote_stores = {}
        self.device_props_updates = Emitter[tuple[str, DeviceProps]]()
        self.preview = Emitter[PreviewSourceEmission]()
        self.preview_revision = Cell(0)
        self.config = INSTRUMENT_CONFIG
        self.hardware_config = INSTRUMENT_CONFIG.hal
        self.fov = ReactiveQuery(fn=self._get_fov)
        self.task_tiles = Cell[list[TaskTile]]([])

    async def _get_fov(self) -> tuple[float, float]:
        return (1.0, 1.0)

    async def open(self) -> None:
        self.events.append("open")
        if self.open_started is not None:
            self.open_started.set()
        if self.open_release is not None:
            await self.open_release.wait()
        if self.open_error is not None:
            raise self.open_error

    async def close(self) -> None:
        self.events.append("close")
        if self.close_error is not None:
            raise self.close_error


@pytest.fixture
def station_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> StationConfig:
    home = tmp_path / ".voxel"
    monkeypatch.setattr(system_module, "_voxel_home", lambda: home)
    return StationConfig(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        name="scope",
    )


def _installed(station: Station, name: str = "instrument") -> Path:
    home = station.instruments_dir / f"{name}.voxel"
    home.mkdir()
    return home


async def test_open_and_close_publish_one_coherent_session_lifecycle(station_config: StationConfig) -> None:
    events: list[str] = []
    open_started = asyncio.Event()
    open_release = asyncio.Event()
    instrument = FakeInstrument(events, open_started=open_started, open_release=open_release)

    def create(home: Path, records: VoxelRecords) -> Instrument:
        del home, records
        return cast("Instrument", instrument)

    station = Station(station_config, instrument_factory=create)
    _installed(station)

    async with station.feed.connect() as connection:
        opening = asyncio.create_task(station.open_session("instrument"))
        await open_started.wait()
        open_release.set()
        session = await opening
        await station.close_session(session.id)
        updates = [await anext(connection) for _ in range(4)]

    assert events == ["open", "close"]
    assert [update.status for update in updates] == [
        StationStatus.OPENING,
        StationStatus.ACTIVE,
        StationStatus.CLOSING,
        StationStatus.IDLE,
    ]
    active_session = updates[1].session
    assert active_session is not None
    assert active_session.info == session
    assert [update.session for update in updates] == [None, active_session, active_session, None]
    assert [update.cursor.seq for update in updates] == [1, 2, 3, 4]
    assert updates[-1].wire_dict()["session"] is None


async def test_close_ends_the_active_session_and_station_feed(station_config: StationConfig) -> None:
    events: list[str] = []
    instrument = FakeInstrument(events)

    def create(home: Path, records: VoxelRecords) -> Instrument:
        del home, records
        return cast("Instrument", instrument)

    station = Station(station_config, instrument_factory=create)
    _installed(station)
    await station.open_session("instrument")

    async with station.feed.connect() as connection:
        await station.close()
        with pytest.raises(StopAsyncIteration):
            await anext(connection)

    await station.close()
    assert events == ["open", "close"]
    assert station.state.value.status is StationStatus.CLOSED
    with pytest.raises(RuntimeError, match="station is closed"):
        await station.open_session("instrument")


async def test_session_open_failure_returns_to_idle_only_after_cleanup(station_config: StationConfig) -> None:
    events: list[str] = []
    instrument = FakeInstrument(events, open_error=ValueError("open failed"))

    def create(home: Path, records: VoxelRecords) -> Instrument:
        del home, records
        return cast("Instrument", instrument)

    station = Station(station_config, instrument_factory=create)
    _installed(station)

    with pytest.raises(ValueError, match="open failed"):
        await station.open_session("instrument")

    snapshot = await station.feed.snapshot()
    assert events == ["open", "close"]
    assert snapshot.status is StationStatus.IDLE
    assert snapshot.session is None
    assert snapshot.error == "ValueError: open failed"


async def test_session_open_cleanup_failure_faults_the_station(station_config: StationConfig) -> None:
    instrument = FakeInstrument(
        [],
        open_error=ValueError("open failed"),
        close_error=OSError("cleanup failed"),
    )

    def create(home: Path, records: VoxelRecords) -> Instrument:
        del home, records
        return cast("Instrument", instrument)

    station = Station(station_config, instrument_factory=create)
    _installed(station)

    with pytest.raises(OSError, match="cleanup failed"):
        await station.open_session("instrument")

    snapshot = await station.feed.snapshot()
    assert snapshot.status is StationStatus.FAULTED
    assert snapshot.session is None
    assert snapshot.error == ("session open failed (ValueError: open failed); cleanup failed (OSError: cleanup failed)")
    with pytest.raises(RuntimeError, match="station is faulted"):
        await station.open_session("instrument")


async def test_close_failure_faults_station_and_retains_session_identity(station_config: StationConfig) -> None:
    instrument = FakeInstrument([])

    def create(home: Path, records: VoxelRecords) -> Instrument:
        del home, records
        return cast("Instrument", instrument)

    station = Station(station_config, instrument_factory=create)
    _installed(station)
    delivered: list[tuple[str, PreviewLayer, bytes]] = []
    unsubscribe = station.feed.frames.subscribe(delivered.append)
    session = await station.open_session("instrument")
    await instrument.preview_revision.set(1)
    state_view = await station.feed.snapshot()
    await instrument.preview.emit(("gfp", PreviewLayer.OVERVIEW, b"VXPS"))
    await asyncio.sleep(0)
    frame = VoxelPreviewPacket.from_packed(delivered[-1][2])
    assert frame.header.seq == 0
    assert frame.header.state_cursor == state_view.cursor
    instrument.close_error = OSError("close failed")

    with pytest.raises(OSError, match="close failed"):
        await station.close_session(session.id)

    snapshot = await station.feed.snapshot()
    assert snapshot.status is StationStatus.FAULTED
    assert snapshot.session is not None
    assert snapshot.session.info.id == session.id
    assert snapshot.session.info.instrument_name == session.instrument_name
    assert snapshot.session.instrument.preview_revision == 1
    assert snapshot.error == "OSError: close failed"
    await instrument.preview.emit(("gfp", PreviewLayer.OVERVIEW, b"ignored"))
    assert len(delivered) == 1
    unsubscribe()
