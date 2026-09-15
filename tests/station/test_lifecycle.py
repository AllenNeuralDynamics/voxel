import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from vxl_records import VoxelRecords
from vxlib.history import HistoryState
from vxlib.reactivity import Cell, Emitter, ReactiveQuery

from rigup import DeviceInterface, DeviceProps
from vxl.instrument import (
    AcquisitionMode,
    ActiveAcquisitionState,
    Instrument,
    InstrumentConfig,
    InstrumentState,
)
from vxl.instrument.models import TaskTile
from vxl.preview import PreviewLayer, PreviewSourceEmission, VoxelPreviewPacket
from vxl.preview.protocol import StagePosition
from vxl.station import Station, StationStatus
from vxl.system import StationConfig


class FakeInstrument:
    def __init__(self, config: InstrumentConfig) -> None:
        self.events: list[str] = []
        self.open_error: Exception | None = None
        self.close_error: Exception | None = None
        self.open_started: asyncio.Event | None = None
        self.open_release: asyncio.Event | None = None
        self.state = Cell(InstrumentState(**config.default.model_dump()))
        self.default = Cell(config.default)
        self.mode = Cell(AcquisitionMode.IDLE)
        self.acquisition = Cell[ActiveAcquisitionState | None](None)
        self.active_profile_id = Cell(next(iter(self.state.value.imaging.profiles)))
        self.history = Cell(HistoryState())
        self.device_interfaces: dict[str, DeviceInterface] = {}
        self.device_props: dict[str, DeviceProps] = {}
        self.remote_stores = {}
        self.device_props_updates = Emitter[tuple[str, DeviceProps]]()
        self.preview = Emitter[PreviewSourceEmission]()
        self.preview_revision = Cell(0)
        self.config = config
        self.hardware_config = config.hal
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
def instrument(instrument_config: InstrumentConfig) -> FakeInstrument:
    return FakeInstrument(instrument_config)


@pytest.fixture
async def station(station_config: StationConfig, instrument: FakeInstrument) -> AsyncIterator[Station]:
    def create(_home: Path, _records: VoxelRecords) -> Instrument:
        return cast("Instrument", instrument)

    station = Station(station_config, instrument_factory=create)
    (station.instruments_dir / "instrument.voxel").mkdir()
    try:
        yield station
    finally:
        if station.state.value.status is StationStatus.FAULTED:
            await station.feed.close()
        else:
            await station.close()


async def test_open_and_close_publish_one_coherent_session_lifecycle(
    station: Station, instrument: FakeInstrument
) -> None:
    events = instrument.events
    open_started = asyncio.Event()
    open_release = asyncio.Event()
    instrument.open_started = open_started
    instrument.open_release = open_release

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


async def test_close_ends_the_active_session_and_station_feed(station: Station, instrument: FakeInstrument) -> None:
    events = instrument.events

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


async def test_session_open_failure_returns_to_idle_only_after_cleanup(
    station: Station, instrument: FakeInstrument
) -> None:
    events = instrument.events
    instrument.open_error = ValueError("open failed")

    with pytest.raises(ValueError, match="open failed"):
        await station.open_session("instrument")

    snapshot = await station.feed.snapshot()
    assert events == ["open", "close"]
    assert snapshot.status is StationStatus.IDLE
    assert snapshot.session is None
    assert snapshot.error == "ValueError: open failed"


async def test_session_open_cleanup_failure_faults_the_station(station: Station, instrument: FakeInstrument) -> None:
    instrument.open_error = ValueError("open failed")
    instrument.close_error = OSError("cleanup failed")

    with pytest.raises(OSError, match="cleanup failed"):
        await station.open_session("instrument")

    snapshot = await station.feed.snapshot()
    assert snapshot.status is StationStatus.FAULTED
    assert snapshot.session is None
    assert snapshot.error == ("session open failed (ValueError: open failed); cleanup failed (OSError: cleanup failed)")
    with pytest.raises(RuntimeError, match="station is faulted"):
        await station.open_session("instrument")


async def test_close_failure_faults_station_and_retains_session_identity(
    station: Station, instrument: FakeInstrument
) -> None:
    delivered: list[tuple[str, PreviewLayer, bytes]] = []
    unsubscribe = station.feed.frames.subscribe(delivered.append)
    session = await station.open_session("instrument")
    await instrument.preview_revision.set(1)
    state_view = await station.feed.snapshot()
    position = StagePosition(x=1, y=2, z=3)
    await instrument.preview.emit(("gfp", PreviewLayer.OVERVIEW, b"VXPS", position))
    await asyncio.sleep(0)
    frame = VoxelPreviewPacket.from_packed(delivered[-1][2])
    assert frame.header.seq == 0
    assert frame.header.state_cursor == state_view.cursor
    assert frame.header.position_um == position
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
    await instrument.preview.emit(("gfp", PreviewLayer.OVERVIEW, b"ignored", None))
    assert len(delivered) == 1
    unsubscribe()


async def test_history_updates_reach_feed_and_unsubscribe_on_session_close(
    station: Station, instrument: FakeInstrument
) -> None:
    await instrument.history.set(HistoryState(undo_label="Edit metadata"))

    session = await station.open_session("instrument")
    async with station.feed.connect() as connection:
        initial = connection.initial
        assert initial.session is not None
        assert initial.session.instrument.history == instrument.history.value
        sequence = initial.cursor.seq
        for history in (
            HistoryState(redo_label="Edit metadata"),
            HistoryState(undo_label="Edit metadata"),
            HistoryState(),
        ):
            await instrument.history.set(history)
            update = await asyncio.wait_for(anext(connection), timeout=1)
            assert update.session is not None
            assert update.session.info == session
            assert update.session.instrument.history == history
            assert update.session.instrument.imaging == instrument.state.value.imaging
            assert update.cursor.seq == sequence + 1
            sequence = update.cursor.seq

    async with station.feed.connect() as reconnected:
        assert reconnected.initial.session is not None
        assert reconnected.initial.session.instrument.history == HistoryState()
        assert reconnected.initial.cursor.seq == sequence

    await station.close_session(session.id)
    assert instrument.history.subs == 0
    closed = await station.feed.snapshot()
    await instrument.history.set(HistoryState(undo_label="Detached edit"))
    snapshot = await station.feed.snapshot()
    assert snapshot.cursor == closed.cursor
    assert snapshot.session is None
