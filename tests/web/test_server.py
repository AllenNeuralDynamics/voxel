"""Tests for the server, from outside: a small service behind it, and readers and HTTP calls in front of it."""

import asyncio
import datetime
import http.client
import json
import socket
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from vxlib.vector import Transform, Vec3D

from vxl.records import Acquisition, Image, Records, Visit
from vxl.storage import StorageSpec
from vxl.web.client import FeedClient
from vxl.web.feed import FeedPublisher
from vxl.web.server import Server
from vxl.web.sockets import FeedSockets, Listener

_TRANSFORM = Transform(
    Vec3D(z=0.0, y=0.0, x=0.0),
    (Vec3D(z=1.0, y=0.0, x=0.0), Vec3D(z=0.0, y=1.0, x=0.0), Vec3D(z=0.0, y=0.0, x=1.0)),
    (2, 4, 4),
)


@dataclass
class _Front:
    """A server in front of a small service: the service's publisher and records, and the server's address."""

    publisher: FeedPublisher
    records: Records
    url: str


async def _echo(request: Request) -> JSONResponse:
    """The service's 1 HTTP route: it answers what it was asked."""
    asked = {
        "method": request.method,
        "path": request.scope["raw_path"].decode(),
        "query": request.url.query,
        "body": (await request.body()).decode(),
        "if_match": request.headers.get("if-match"),
    }
    return JSONResponse(asked, status_code=202, headers={"ETag": '"v1"', "Vxl-Feed-Cursor": '"a:1"'})


@pytest.fixture
async def front(tmp_path: Path) -> AsyncIterator[_Front]:
    publisher = FeedPublisher("stations.s")
    routes = [
        *FeedSockets(publisher).routes("/api/stations/s"),
        Route("/api/stations/s/{path:path}", _echo, methods=["PATCH"]),
    ]
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / "store" / spec.path)
    (tmp_path / "store").mkdir()
    (tmp_path / "store" / "image.bin").write_bytes(bytes(range(100)))
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<html>the app</html>")
    (tmp_path / "web" / "app.js").write_text("run()")
    async with Listener(Starlette(routes=routes)) as upstream:
        server = Server(
            f"http://127.0.0.1:{upstream.port}/api/stations/s",
            records=records.path,
            data=tmp_path / "store",
            web=tmp_path / "web",
        )
        async with server, Listener(server.app) as listener:
            yield _Front(publisher, records, f"http://127.0.0.1:{listener.port}")


def _request(url: str, method: str, body: bytes | None, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
    address = urlsplit(url)
    connection = http.client.HTTPConnection(address.netloc)
    target = address.path + (f"?{address.query}" if address.query else "")
    connection.request(method, target, body=body, headers=headers)
    answer = connection.getresponse()
    content = answer.read()
    connection.close()
    return answer.status, {name.lower(): value for name, value in answer.getheaders()}, content


async def call(
    url: str, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], bytes]:
    """1 HTTP request: the status, the headers and the body of the answer."""
    return await asyncio.to_thread(_request, url, method, body, headers or {})


async def test_a_reader_gets_the_feed_of_the_service_with_its_own_cursors(front: _Front) -> None:
    front.publisher.publish({"status": "idle"})
    reader = FeedClient(f"{front.url.replace('http', 'ws', 1)}/api/stations/s")

    async with asyncio.timeout(10), aclosing(reader.state()) as messages:
        kept = await anext(messages)
        while "stations.s.status" not in kept.topics:  # a reader can be there before the service's first message
            kept = kept.merge(await anext(messages))
        front.publisher.publish({"status": "active"})
        change = await anext(messages)

    assert kept.full
    assert kept.topics == {"stations.s.status": "idle"}
    assert (change.full, change.topics) == (False, {"stations.s.status": "active"})
    assert change.cursor == front.publisher.snapshot().cursor


async def test_a_frame_passes_unopened_and_keeps_its_link_to_the_state(front: _Front) -> None:
    reader = FeedClient(f"{front.url.replace('http', 'ws', 1)}/api/stations/s")
    frame = bytes(range(256)) * 100

    async with asyncio.timeout(10), aclosing(reader.frames()) as messages:
        reading = asyncio.create_task(anext(messages))
        while not reading.done():  # a frame goes only to readers that are connected, so send until one arrives
            front.publisher.publish_frame("instrument.frames.camera.overview", frame, None)
            await asyncio.sleep(0.01)
        message = await reading

    ((topic, value),) = message.topics.items()
    assert topic == "stations.s.instrument.frames.camera.overview"
    assert value.frame == frame
    assert value.state == front.publisher.snapshot().cursor


async def test_a_command_reaches_the_service_and_its_answer_comes_back_unchanged(front: _Front) -> None:
    status, headers, content = await call(
        f"{front.url}/api/stations/s/instrument/state/plan/t%2F1?dry=1",
        "PATCH",
        b'{"label": "x"}',
        {"If-Match": '"v0"'},
    )

    assert status == 202
    assert (headers["etag"], headers["vxl-feed-cursor"]) == ('"v1"', '"a:1"')
    assert json.loads(content) == {
        "method": "PATCH",
        "path": "/api/stations/s/instrument/state/plan/t%2F1",
        "query": "dry=1",
        "body": '{"label": "x"}',
        "if_match": '"v0"',
    }


async def test_a_service_that_does_not_answer_gives_a_502_problem() -> None:
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    server = Server(f"http://127.0.0.1:{port}/api/stations/s")

    async with server, Listener(server.app) as listener:
        status, headers, content = await call(f"http://127.0.0.1:{listener.port}/api/stations/s/session:open", "POST")

    assert status == 502
    assert headers["content-type"] == "application/problem+json"
    assert json.loads(content)["status"] == 502


async def test_the_server_reads_the_feed_again_after_the_service_refuses_it() -> None:
    publisher = FeedPublisher("stations.s")
    publisher.publish({"status": "idle"})
    feed = Starlette(routes=FeedSockets(publisher).routes("/api/stations/s"))

    async with asyncio.timeout(20), Listener(Starlette()) as no_feed:  # a program that refuses the feed sockets
        server = Server(f"http://127.0.0.1:{no_feed.port}/api/stations/s")
        async with server, Listener(server.app) as listener:
            reader = FeedClient(f"ws://127.0.0.1:{listener.port}/api/stations/s")
            async with aclosing(reader.state()) as messages:
                empty = await anext(messages)
                await no_feed.__aexit__(None, None, None)
                async with Listener(feed, port=no_feed.port):
                    kept = await anext(messages)

    assert (empty.full, empty.topics) == (True, {})
    assert kept.topics == {"stations.s.status": "idle"}


@pytest.mark.parametrize("upstream", ["http://127.0.0.1:5600", "http://127.0.0.1:5600/stations/s"])
def test_an_upstream_that_is_no_path_under_api_is_refused(upstream: str) -> None:
    with pytest.raises(ValueError, match="under /api/"):
        Server(upstream)


async def test_the_server_says_which_service_it_fronts_also_while_the_service_is_gone() -> None:
    server = Server("http://127.0.0.1:9/api/stations/s")

    async with server, Listener(server.app) as listener:
        fronted = await call(f"http://127.0.0.1:{listener.port}/api")
        other = await call(f"http://127.0.0.1:{listener.port}/api/stations/other/instruments")

    assert (fronted[0], json.loads(fronted[2])) == (200, {"service": "/api/stations/s"})
    assert (other[0], other[1]["content-type"]) == (404, "application/problem+json")


async def test_a_data_folder_that_does_not_exist_yet_answers_404(tmp_path: Path) -> None:
    server = Server("http://127.0.0.1:9/api/stations/s", data=tmp_path / "later")

    async with server, Listener(server.app) as listener:
        status, headers, _ = await call(f"http://127.0.0.1:{listener.port}/api/stations/s/data/image.bin")

    assert (status, headers["content-type"]) == (404, "application/problem+json")


async def test_the_history_gives_the_stored_acquisitions_and_log_lines(front: _Front) -> None:
    acquisition = Acquisition(
        id=uuid4(),
        operator="ana",
        host="rig",
        created_at=datetime.datetime.now(tz=datetime.UTC),
        storage=StorageSpec(path=PurePosixPath("runs/1")),
        instrument_config={"id": "bench"},
        instrument_state={},
        visits=[Visit(task="a", profile="main", channels={"main": {"camera": Image(transform=_TRANSFORM)}})],
    )
    await front.records.acquisitions.save(acquisition, write_file=False)
    line = await front.records.logs.append(
        emitted_at=datetime.datetime.now(tz=datetime.UTC), level=30, logger="tests.server", message="the laser is warm"
    )
    history = f"{front.url}/api/stations/s/history"

    listed = await call(f"{history}/acquisitions")
    none = await call(f"{history}/acquisitions?status=completed")
    one = await call(f"{history}/acquisitions/{acquisition.id}")
    missing = await call(f"{history}/acquisitions/{uuid4()}")
    lines = await call(f"{history}/logs?after_seq={line.seq - 1}")
    refused = await call(f"{history}/logs?limit=0")

    assert [answer[0] for answer in (listed, none, one, missing, lines, refused)] == [200, 200, 200, 404, 200, 422]
    assert [(item["id"], item["instrument"]) for item in json.loads(listed[2])] == [(str(acquisition.id), "bench")]
    assert json.loads(none[2]) == []
    assert json.loads(one[2])["operator"] == "ana"
    assert json.loads(one[2])["status"] == json.loads(listed[2])[0]["status"]
    assert json.loads(lines[2]) == [line.model_dump(mode="json")]


async def test_image_files_are_served_in_parts_and_cannot_be_changed(front: _Front) -> None:
    part = await call(f"{front.url}/api/stations/s/data/image.bin", headers={"Range": "bytes=10-19"})
    written = await call(f"{front.url}/api/stations/s/data/image.bin", "PUT", b"new")

    assert (part[0], part[2]) == (206, bytes(range(10, 20)))
    assert written[0] == 405


async def test_the_web_app_is_served_and_its_own_routes_get_the_index_page(front: _Front) -> None:
    index = await call(f"{front.url}/")
    page = await call(f"{front.url}/stations/s/run")
    script = await call(f"{front.url}/app.js")
    no_data = await call(f"{front.url}/api/nothing")

    assert (index[0], page[0], script[0], no_data[0]) == (200, 200, 200, 404)
    assert index[2] == page[2] == b"<html>the app</html>"
    assert script[2] == b"run()"
    assert no_data[1]["content-type"] == "application/problem+json"


def test_the_server_imports_the_shared_web_files_and_nothing_else_of_vxl() -> None:
    code = "import sys, vxl.web.server; print(*sorted(m for m in sys.modules if m.split('.')[0] == 'vxl'))"

    loaded = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()

    assert loaded
    assert set(loaded) == {
        "vxl",
        "vxl.web",
        "vxl.web.client",
        "vxl.web.feed",
        "vxl.web.problems",
        "vxl.web.server",
        "vxl.web.sockets",
    }
