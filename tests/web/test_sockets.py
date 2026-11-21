"""Tests for the feed over real sockets: a publisher behind its 2 WebSockets, read by the client."""

import asyncio
from contextlib import aclosing

import pytest
from starlette.applications import Starlette
from vxlib.vector import StagePosition

from vxl.web.client import FeedClient
from vxl.web.feed import FeedPublisher
from vxl.web.sockets import FeedSockets, Listener


def _app(publisher: FeedPublisher) -> Starlette:
    return Starlette(routes=FeedSockets(publisher).routes("/api/stations/s"))


async def test_a_reader_gets_a_full_message_then_each_change() -> None:
    publisher = FeedPublisher("stations.s")
    publisher.publish({"status": "idle"})

    async with Listener(_app(publisher)) as listener, asyncio.timeout(5):
        client = FeedClient(f"ws://127.0.0.1:{listener.port}/api/stations/s")
        async with aclosing(client.state()) as messages:
            first = await anext(messages)
            publisher.publish({"status": "active"})
            second = await anext(messages)

    assert (first.full, first.topics) == (True, {"stations.s.status": "idle"})
    assert (second.full, second.topics) == (False, {"stations.s.status": "active"})
    assert second.cursor.seq == first.cursor.seq + 1


async def test_a_frame_arrives_as_the_bytes_that_were_sent() -> None:
    publisher = FeedPublisher("stations.s")
    position = StagePosition(x=1, y=2, z=3)
    frame = bytes(range(256)) * 400

    async with Listener(_app(publisher)) as listener, asyncio.timeout(5):
        client = FeedClient(f"ws://127.0.0.1:{listener.port}/api/stations/s")
        async with aclosing(client.frames()) as messages:
            reading = asyncio.create_task(anext(messages))
            while not reading.done():  # a frame goes only to a reader that is connected, so send until one arrives
                publisher.publish_frame("instrument.frames.camera.overview", frame, position)
                await asyncio.sleep(0.01)
            message = await reading

    ((topic, value),) = message.topics.items()
    assert topic == "stations.s.instrument.frames.camera.overview"
    assert (value.frame, value.position_um) == (frame, position)
    assert value.state == publisher.snapshot().cursor


async def test_a_reader_connects_again_and_starts_over_from_a_full_message() -> None:
    first_publisher, second_publisher = FeedPublisher("stations.s"), FeedPublisher("stations.s")
    first_publisher.publish({"status": "idle"})
    second_publisher.publish({"status": "active"})

    async with asyncio.timeout(10):
        async with Listener(_app(first_publisher)) as listener:
            port = listener.port
            client = FeedClient(f"ws://127.0.0.1:{port}/api/stations/s")
            messages = client.state()
            before = await anext(messages)
        async with Listener(_app(second_publisher), port=port), aclosing(messages):
            after = await anext(messages)

    assert (before.full, before.topics) == (True, {"stations.s.status": "idle"})
    assert (after.full, after.topics) == (True, {"stations.s.status": "active"})
    assert after.cursor.stream_id != before.cursor.stream_id


async def test_a_port_that_is_taken_raises() -> None:
    async with Listener(Starlette()) as first:
        with pytest.raises(OSError, match="in use"):
            await Listener(Starlette(), port=first.port).__aenter__()
