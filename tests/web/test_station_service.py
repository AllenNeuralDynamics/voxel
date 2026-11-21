"""Tests for the station service: its HTTP operations and its feed, over real sockets on a local port."""

import asyncio
import datetime
from collections.abc import AsyncIterator
from contextlib import aclosing
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from vxlib.vector import Transform, Vec3D

from vxl import system as system_module
from vxl.records import Acquisition, Image, Visit
from vxl.station.config import StationConfig
from vxl.storage import StorageSpec
from vxl.web.client import FeedClient
from vxl.web.problems import ProblemDetails
from vxl.web.server import Server
from vxl.web.sockets import Listener
from vxl.web.station.instrument import InstrumentRouter
from vxl.web.station.service import StationService

from .support import TEMPLATE, call

_TRANSFORM = Transform(
    Vec3D(z=0.0, y=0.0, x=0.0),
    (Vec3D(z=1.0, y=0.0, x=0.0), Vec3D(z=0.0, y=1.0, x=0.0), Vec3D(z=0.0, y=0.0, x=1.0)),
    (2, 4, 4),
)


@pytest.fixture
async def service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[StationService]:
    monkeypatch.setattr(system_module, "voxel_home", lambda: tmp_path / ".voxel")
    config = StationConfig(id=UUID("12345678-1234-5678-1234-567812345678"), name="scope")
    async with StationService(config, port=0) as running:
        await running.station.create_instrument("bench", TEMPLATE)
        yield running


async def test_a_session_opens_and_a_device_changes_over_http_and_the_feed_shows_both(service: StationService) -> None:
    prefix = f"stations.{service.station.config.id}"
    reader = FeedClient(service.url.replace("http", "ws", 1))

    async with asyncio.timeout(20), aclosing(reader.state()) as messages:
        before = await anext(messages)
        listed = await call(service.url, "GET", "/instruments")
        opened = await call(service.url, "POST", "/session:open", {"instrument": "bench"})
        changed = await call(service.url, "PATCH", "/instrument/devices/camera", {"exposure_time_ms": 12.5})
        kept, exposure = before, f"{prefix}.instrument.devices.camera.props.exposure_time_ms"
        while not (isinstance(value := kept.topics.get(exposure), dict) and value.get("value") == 12.5):
            kept = kept.merge(await anext(messages))

    assert before.topics[f"{prefix}.status"] == "idle"
    assert listed[0] == 200
    assert listed[2]["bench"]["ok"]
    assert opened[0] == 200
    assert opened[2]["instrument_name"] == "bench"
    assert opened[1]["vxl-feed-cursor"].startswith('"')
    assert changed[0] == 200
    assert kept.topics[f"{prefix}.session"] == opened[2]


async def test_a_read_carries_a_tag_and_answers_304_when_nothing_changed(service: StationService) -> None:
    await call(service.url, "POST", "/session:open", {"instrument": "bench"})

    first = await call(service.url, "GET", "/instrument/state/profiles")
    again = await call(service.url, "GET", "/instrument/state/profiles", headers={"If-None-Match": first[1]["etag"]})
    one = await call(service.url, "GET", "/instrument/state/profiles/main")
    edit = {"label": "first light"}
    stale = await call(service.url, "PATCH", "/instrument/state/profiles/main", edit, {"If-Match": '"old"'})
    fresh = await call(service.url, "PATCH", "/instrument/state/profiles/main", edit, {"If-Match": one[1]["etag"]})

    assert (first[0], again[0], one[0], stale[0], fresh[0]) == (200, 304, 200, 412, 200)
    assert "main" in first[2]
    assert "vxl-feed-cursor" not in first[1]
    assert fresh[2]["label"] == "first light"
    assert fresh[1]["etag"] != one[1]["etag"]


async def test_refusals_answer_as_problems(service: StationService) -> None:
    no_session = await call(service.url, "GET", "/instrument/state/profiles")
    unknown = await call(service.url, "POST", "/session:open", {"instrument": "nope"})
    await call(service.url, "POST", "/session:open", {"instrument": "bench"})
    busy = await call(service.url, "POST", "/session:open", {"instrument": "bench"})
    no_device = await call(service.url, "PATCH", "/instrument/devices/nope", {"exposure_time_ms": 1})
    no_route = await call(service.url, "GET", "/nowhere")

    assert [answer[0] for answer in (no_session, unknown, busy, no_device, no_route)] == [409, 404, 409, 404, 404]
    for answer in (no_session, unknown, busy, no_device, no_route):
        assert answer[1]["content-type"] == "application/problem+json"
        assert answer[2]["status"] == answer[0]
        assert answer[2]["detail"]


async def test_closing_the_session_closes_the_instrument_routes(service: StationService) -> None:
    await call(service.url, "POST", "/session:open", {"instrument": "bench"})

    closed = await call(service.url, "POST", "/session:close")
    after = await call(service.url, "GET", "/instrument/state/profiles")

    assert (closed[0], after[0]) == (204, 409)


async def test_a_window_reaches_the_station_through_its_server(service: StationService) -> None:
    prefix = f"stations.{service.station.config.id}"
    server = Server(service.url, records=service.station.records.path)

    async with server, Listener(server.app) as listener, asyncio.timeout(20):
        url = f"http://127.0.0.1:{listener.port}/api/stations/{service.station.config.id}"
        reader = FeedClient(url.replace("http", "ws", 1))
        async with aclosing(reader.state()) as messages:
            opened = await call(url, "POST", "/session:open", {"instrument": "bench"})
            kept = await anext(messages)
            while f"{prefix}.session" not in kept.topics:
                kept = kept.merge(await anext(messages))
        lines = await call(url, "GET", "/history/logs")

    assert opened[0] == 200
    assert "vxl-feed-cursor" in opened[1]
    assert kept.topics[f"{prefix}.session"] == opened[2]
    assert kept.cursor.stream_id == opened[1]["vxl-feed-cursor"].strip('"').split(":")[0]
    assert lines[0] == 200


async def test_the_routes_of_an_instrument_work_in_any_app_and_describe_themselves(service: StationService) -> None:
    session = await service.station.open_session("bench")
    app = FastAPI()
    ProblemDetails.install(app, InstrumentRouter.statuses)

    async with service.station.instrument(session.id) as instrument:
        app.include_router(InstrumentRouter(instrument), prefix="/bench")
        async with Listener(app) as listener:
            url = f"http://127.0.0.1:{listener.port}/bench"
            profiles = await call(url, "GET", "/state/profiles")
            edited = await call(url, "PATCH", "/state/profiles/main", {"label": "no station"})
            missing = await call(url, "PATCH", "/state/profiles/nope", {"label": "x"})
            refused = await call(url, "PATCH", "/state/profiles/main", {"label": 5})
            page = await call(url, "GET", "/openapi.json")

    assert (profiles[0], edited[0], missing[0], refused[0], page[0]) == (200, 200, 404, 422, 200)
    assert edited[2]["label"] == "no station"
    assert (missing[1]["content-type"], refused[1]["content-type"]) == ("application/problem+json",) * 2
    assert "label" in refused[2]["detail"], refused[2]
    assert "/state/profiles/{profile_id}" in page[2]["paths"]
    assert "patch" in page[2]["paths"]["/state/profiles/{profile_id}"]
    assert "ProblemDetails" in page[2]["components"]["schemas"]


async def test_an_operation_that_gives_back_an_id_answers_it_as_text(service: StationService) -> None:
    await call(service.url, "POST", "/session:open", {"instrument": "bench"})

    started = await call(service.url, "POST", "/instrument/run:start")

    assert (started[0], started[2]) == (200, str(UUID(int=42)))


async def test_a_request_that_cannot_apply_is_refused_with_the_status_that_says_why(service: StationService) -> None:
    await call(service.url, "POST", "/session:open", {"instrument": "bench"})
    exposure = {"exposure_time_ms": 5.0}

    not_json = await call(service.url, "PATCH", "/instrument/devices/camera", {"exposure_time_ms": float("nan")})
    stale = await call(service.url, "PATCH", "/instrument/devices/camera", exposure, {"If-Match": '"old"'})
    busy = await call(service.url, "POST", "/instrument/run:stop")
    slash = await call(service.url, "GET", "/instrument/state/profiles/")
    no_method = await call(service.url, "DELETE", "/instrument/state/profiles/main")

    assert [answer[0] for answer in (not_json, stale, busy, slash, no_method)] == [400, 412, 409, 404, 405]
    assert "NaN" in not_json[2]["detail"]
    assert busy[2]["detail"] == "the run holds the camera"
    assert "location" not in slash[1]
    assert "PATCH" in no_method[1]["allow"]


async def test_a_second_service_of_the_same_station_is_refused_and_ends_no_acquisition(service: StationService) -> None:
    running = Acquisition(
        id=uuid4(),
        operator="ana",
        host="rig",
        created_at=datetime.datetime.now(tz=datetime.UTC),
        storage=StorageSpec(path=PurePosixPath("runs/1")),
        instrument_config={"id": "bench"},
        instrument_state={},
        visits=[Visit(task="a", profile="main", channels={"main": {"camera": Image(transform=_TRANSFORM)}})],
    )
    await service.station.records.acquisitions.save(running, write_file=False)
    port = int(service.url.split(":")[2].split("/")[0])

    with pytest.raises(OSError, match="in use"):
        await StationService(service.station.config, port=port).__aenter__()

    assert await service.station.records.acquisitions.interrupt_open() == [running.id]
