from uuid import UUID

import pytest
from vxlib.history import HistoryState
from vxlib.reactivity import Cell

from vxl.instrument import AcquisitionMode, InstrumentConfig
from vxl.station import (
    InstrumentView,
    SessionInfo,
    SessionView,
    StationFeed,
    StationFeedLaggedError,
    StationFeedView,
    StationState,
    StationStatus,
)
from vxl.system import StationConfig


@pytest.fixture
def session(instrument_config: InstrumentConfig) -> SessionView:
    return SessionView(
        info=SessionInfo(
            id=UUID("87654321-4321-8765-4321-876543218765"),
            instrument_name="instrument",
        ),
        instrument=InstrumentView(
            **instrument_config.default.model_dump(),
            config=instrument_config,
            mode=AcquisitionMode.IDLE,
            active_profile_id="single_gfp",
            preview_revision=0,
            fov=None,
            history=HistoryState(),
            task_tiles=[],
            devices={},
            acquisition=None,
            remote_stores={},
        ),
    )


async def test_connection_snapshot_is_followed_by_ordered_updates(
    station_config: StationConfig, session: SessionView
) -> None:
    state = Cell(StationState())
    feed = StationFeed(station_config.info, state)
    try:
        async with feed.connect() as connection:
            assert connection.initial.status is StationStatus.IDLE
            assert connection.initial.cursor.seq == 0

            await state.set(StationState())
            await state.set(StationState(status=StationStatus.OPENING))
            await state.set(StationState(status=StationStatus.ACTIVE, session=session))

            opening = await anext(connection)
            active = await anext(connection)

        assert opening.status is StationStatus.OPENING
        assert active.status is StationStatus.ACTIVE
        assert active.session == session
        assert [opening.cursor.seq, active.cursor.seq] == [1, 2]
        assert opening.cursor.stream_id == connection.initial.cursor.stream_id == active.cursor.stream_id
    finally:
        await feed.close()


async def test_reconnection_starts_from_latest_snapshot(station_config: StationConfig, session: SessionView) -> None:
    state = Cell(StationState())
    feed = StationFeed(station_config.info, state)
    try:
        async with feed.connect() as first:
            await state.set(StationState(status=StationStatus.OPENING))
            assert (await anext(first)).cursor.seq == 1

        await state.set(StationState(status=StationStatus.ACTIVE, session=session))

        async with feed.connect() as reconnected:
            assert reconnected.initial.status is StationStatus.ACTIVE
            assert reconnected.initial.cursor.seq == 2

            await state.set(StationState(status=StationStatus.CLOSING, session=session))
            closing = await anext(reconnected)

        assert closing.status is StationStatus.CLOSING
        assert closing.cursor.seq == 3
    finally:
        await feed.close()


async def test_slow_connection_is_disconnected_without_affecting_other_consumers(
    station_config: StationConfig, session: SessionView
) -> None:
    state = Cell(StationState())
    feed = StationFeed(station_config.info, state, update_buffer_size=1)
    try:
        async with feed.connect() as slow, feed.connect() as current:
            await state.set(StationState(status=StationStatus.OPENING))
            assert (await anext(current)).status is StationStatus.OPENING

            await state.set(StationState(status=StationStatus.ACTIVE, session=session))

            assert (await anext(current)).status is StationStatus.ACTIVE
            with pytest.raises(StationFeedLaggedError, match="fell behind"):
                await anext(slow)
    finally:
        await feed.close()


@pytest.mark.parametrize(
    "history",
    [HistoryState(undo_label="Edit metadata"), HistoryState(redo_label="Edit metadata"), HistoryState()],
)
async def test_history_serialization_preserves_labels_and_explicit_nulls(
    station_config: StationConfig, session: SessionView, history: HistoryState
) -> None:
    session = session.model_copy(update={"instrument": session.instrument.model_copy(update={"history": history})})
    state = Cell(StationState(status=StationStatus.ACTIVE, session=session))
    feed = StationFeed(station_config.info, state)
    try:
        view = await feed.snapshot()
        wire = view.wire_dict()
        assert wire["session"] == session.model_dump(mode="json", exclude_none=False)
        decoded = StationFeedView.model_validate(wire)
        assert decoded.session is not None
        assert decoded.session.instrument.history == history
    finally:
        await feed.close()
