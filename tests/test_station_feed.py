from pathlib import Path
from uuid import UUID

import pytest

from vxl.instrument import AcquisitionMode, InstrumentConfig
from vxl.station import (
    InstrumentView,
    SessionInfo,
    SessionView,
    StationFeed,
    StationFeedLaggedError,
    StationState,
    StationStatus,
)
from vxl.system import StationInfo
from vxlib import Cell, load_yaml

STATION = StationInfo(id=UUID("12345678-1234-5678-1234-567812345678"), name="scope")
CONFIG = load_yaml(
    Path(__file__).parents[1] / "src/vxl/station/templates/builtins/simulated-local.voxel.yaml",
    InstrumentConfig,
)
SESSION = SessionView(
    info=SessionInfo(
        id=UUID("87654321-4321-8765-4321-876543218765"),
        instrument_name="instrument",
    ),
    instrument=InstrumentView(
        **CONFIG.default.model_dump(),
        config=CONFIG,
        mode=AcquisitionMode.IDLE,
        active_profile_id="single_gfp",
        preview_revision=0,
        fov=None,
        routing_targets={},
        task_tiles=[],
        devices={},
        acquisition=None,
        remote_stores={},
    ),
)


async def test_connection_snapshot_is_followed_by_ordered_updates() -> None:
    state = Cell(StationState())
    feed = StationFeed(STATION, state)

    async with feed.connect() as connection:
        assert connection.initial.status is StationStatus.IDLE
        assert connection.initial.cursor.seq == 0

        await state.set(StationState())
        await state.set(StationState(status=StationStatus.OPENING))
        await state.set(StationState(status=StationStatus.ACTIVE, session=SESSION))

        opening = await anext(connection)
        active = await anext(connection)

    assert opening.status is StationStatus.OPENING
    assert active.status is StationStatus.ACTIVE
    assert active.session == SESSION
    assert [opening.cursor.seq, active.cursor.seq] == [1, 2]
    assert opening.cursor.stream_id == connection.initial.cursor.stream_id == active.cursor.stream_id


async def test_reconnection_starts_from_latest_snapshot() -> None:
    state = Cell(StationState())
    feed = StationFeed(STATION, state)

    async with feed.connect() as first:
        await state.set(StationState(status=StationStatus.OPENING))
        assert (await anext(first)).cursor.seq == 1

    await state.set(StationState(status=StationStatus.ACTIVE, session=SESSION))

    async with feed.connect() as reconnected:
        assert reconnected.initial.status is StationStatus.ACTIVE
        assert reconnected.initial.cursor.seq == 2

        await state.set(StationState(status=StationStatus.CLOSING, session=SESSION))
        closing = await anext(reconnected)

    assert closing.status is StationStatus.CLOSING
    assert closing.cursor.seq == 3


async def test_slow_connection_is_disconnected_without_affecting_other_consumers() -> None:
    state = Cell(StationState())
    feed = StationFeed(STATION, state, update_buffer_size=1)

    async with feed.connect() as slow, feed.connect() as current:
        await state.set(StationState(status=StationStatus.OPENING))
        assert (await anext(current)).status is StationStatus.OPENING

        await state.set(StationState(status=StationStatus.ACTIVE, session=SESSION))

        assert (await anext(current)).status is StationStatus.ACTIVE
        with pytest.raises(StationFeedLaggedError, match="fell behind"):
            await anext(slow)
