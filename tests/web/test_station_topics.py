"""Tests for the station as feed topics: what goes out when the station changes."""

import asyncio
import datetime
import logging
from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

import pytest
from vxlib.reactivity import Emitter
from vxlib.vector import Transform, Vec3D

from vxl import system as system_module
from vxl.live import LiveLayer, LiveSourceEmission
from vxl.records import Acquisition, Image, Visit
from vxl.station.config import StationConfig
from vxl.station.station import Station
from vxl.storage import StorageSpec
from vxl.web.feed import FeedPublisher
from vxl.web.station.topics import StationTopics

from .support import TEMPLATE

_TRANSFORM = Transform(
    Vec3D(z=0.0, y=0.0, x=0.0),
    (Vec3D(z=1.0, y=0.0, x=0.0), Vec3D(z=0.0, y=1.0, x=0.0), Vec3D(z=0.0, y=0.0, x=1.0)),
    (2, 4, 4),
)


@pytest.fixture
async def station(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Station]:
    monkeypatch.setattr(system_module, "voxel_home", lambda: tmp_path / ".voxel")
    station = Station(StationConfig(id=UUID("12345678-1234-5678-1234-567812345678"), name="scope"))
    try:
        yield station
    finally:
        await station.close()


def _publish(station: Station, live: Emitter[LiveSourceEmission] | None = None) -> tuple[FeedPublisher, StationTopics]:
    """A publisher with the prefix ``stations.s`` that the station publishes its topics to."""
    publisher = FeedPublisher("stations.s")
    return publisher, StationTopics(station.config.info, station.view, live or station.live, station.records, publisher)


async def test_a_change_publishes_only_the_topics_that_changed(station: Station) -> None:
    await station.create_instrument("bench", TEMPLATE)
    info = await station.open_session("bench")
    publisher, topics = _publish(station)

    with publisher.connect() as connection:
        first = await anext(connection)
        async with station.instrument(info.id) as instrument:
            await instrument.set_device_properties("camera", {"exposure_time_ms": 12.5})
        changed = await anext(connection)
        kept, whole = publisher.snapshot(), StationTopics.view_topics(station.config.info, station.view.value)

    assert first.full
    assert "stations.s.instrument.devices.camera.props.exposure_time_ms" in changed.topics
    assert "stations.s.instrument.devices.camera.interface" not in changed.topics
    assert "stations.s.instrument.config" not in changed.topics
    assert first.merge(changed) == kept
    assert kept.topics == {f"stations.s.{topic}": value for topic, value in whole.items()}
    topics.close()


async def test_frames_go_out_under_their_camera_and_layer_while_a_session_is_active(station: Station) -> None:
    live = Emitter[LiveSourceEmission]()
    publisher, topics = _publish(station, live)
    await station.create_instrument("bench", TEMPLATE)

    with publisher.connect() as state, publisher.connect_frames() as frames:
        await live.emit(("camera", LiveLayer.OVERVIEW, b"no session", None))
        info = await station.open_session("bench")
        await live.emit(("camera", LiveLayer.OVERVIEW, b"frame", None))
        message = await anext(frames)
        await live.emit(("camera", LiveLayer.OVERVIEW, b"waits when the session ends", None))
        await station.close_session(info.id)
        publisher.close()
        left = [frame async for frame in frames]
        (last,) = [view async for view in state]

    assert {topic: value.frame for topic, value in message.topics.items()} == {
        "stations.s.instrument.frames.camera.overview": b"frame"
    }
    assert left == []
    assert last.full
    assert last.topics.keys() == {"stations.s.station", "stations.s.status"}
    topics.close()


async def test_a_saved_acquisition_publishes_only_the_fields_and_visits_that_changed(station: Station) -> None:
    publisher, topics = _publish(station)
    visits = [
        Visit(task=task, profile="main", channels={"main": {"camera": Image(transform=_TRANSFORM)}}) for task in "ab"
    ]
    acquisition = Acquisition(
        id=uuid4(),
        operator="ana",
        host="rig",
        created_at=datetime.datetime.now(tz=datetime.UTC),
        storage=StorageSpec(path=PurePosixPath("runs/1")),
        instrument_config={"id": "bench"},
        instrument_state={},
        visits=visits,
    )
    written = Image(transform=_TRANSFORM, frames_collected=1)
    progress = [visits[0], visits[1].model_copy(update={"channels": {"main": {"camera": written}}})]

    with publisher.connect() as connection:
        await anext(connection)
        await station.records.acquisitions.save(acquisition, write_file=False)
        created = await anext(connection)
        later = acquisition.model_copy(update={"revision": 2, "visits": progress})
        await station.records.acquisitions.save(later, write_file=False)
        changed = await anext(connection)

    assert created.topics["stations.s.acquisition.id"] == str(acquisition.id)
    assert {"stations.s.acquisition.visits.0", "stations.s.acquisition.visits.1"} <= created.topics.keys()
    assert changed.topics.keys() == {"stations.s.acquisition.revision", "stations.s.acquisition.visits.1"}
    topics.close()


async def test_the_newest_stored_acquisition_is_shown_and_an_older_save_does_not_replace_it(station: Station) -> None:
    now = datetime.datetime.now(tz=datetime.UTC)
    older, newer = (
        Acquisition(
            id=uuid4(),
            operator="ana",
            host="rig",
            created_at=now - datetime.timedelta(hours=hours),
            storage=StorageSpec(path=PurePosixPath(f"runs/{hours}")),
            instrument_config={"id": "bench"},
            instrument_state={},
            visits=[Visit(task="a", profile="main", channels={"main": {"camera": Image(transform=_TRANSFORM)}})],
        )
        for hours in (2, 1)
    )
    for acquisition in (newer, older):
        await station.records.acquisitions.save(acquisition, write_file=False)
    publisher, topics = _publish(station)

    await topics.show_newest()
    await station.records.acquisitions.save(older.ended("interrupted", now, []), write_file=False)

    assert publisher.snapshot().topics["stations.s.acquisition.id"] == str(newer.id)
    topics.close()


async def test_the_newest_log_line_is_a_topic(station: Station) -> None:
    await station.open()
    publisher, topics = _publish(station)

    logging.getLogger("vxl.test_station").warning("kept")
    await station.records.logs.mark()  # wait until the line is stored
    newest = (await station.records.logs.tail())[-1]

    assert publisher.snapshot().topics["stations.s.log"] == newest.model_dump(mode="json")
    topics.close()


async def test_a_reader_sees_the_station_close_before_the_feed_ends(station: Station) -> None:
    publisher, topics = _publish(station)

    with publisher.connect() as connection:
        await station.close()
        publisher.close()
        async with asyncio.timeout(1):
            seen = [message async for message in connection]

    assert seen[-1].topics["stations.s.status"] == "closed"
    topics.close()
