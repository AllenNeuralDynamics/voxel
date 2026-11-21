"""Tests for the feed's publisher: what each connection gets, and when."""

import pytest
from vxlib.vector import StagePosition

from vxl.web.feed import FeedPublisher


async def test_a_new_connection_starts_with_every_topic_under_the_prefix() -> None:
    publisher = FeedPublisher("stations.s1")
    publisher.publish({"status": "idle", "error": "no rig"})
    publisher.publish({"error": None})

    with publisher.connect() as connection:
        first = await anext(connection)

    assert first.full
    assert first.topics == {"stations.s1.status": "idle"}
    assert first == publisher.snapshot()


async def test_a_slow_reader_gets_1_message_with_the_newest_value_of_each_topic() -> None:
    publisher = FeedPublisher("lab")

    with publisher.connect() as connection:
        first = await anext(connection)
        for value in range(5):
            publisher.publish({"a": value})
        publisher.publish({"b": 1})
        waiting = await anext(connection)

    assert not waiting.full
    assert waiting.topics == {"lab.a": 4, "lab.b": 1}
    assert first.merge(waiting) == publisher.snapshot()


async def test_replace_starts_every_reader_over_and_drops_the_frames_that_wait() -> None:
    publisher = FeedPublisher("lab")
    publisher.publish({"a": 1, "b": 2})

    with publisher.connect() as state, publisher.connect_frames() as frames:
        await anext(state)
        publisher.publish({"b": 3})
        publisher.publish_frame("frames.camera.overview", b"old", None)
        publisher.replace({"a": 3, "gone": None})
        publisher.close()
        left = [message async for message in frames]
        (last,) = [message async for message in state]

    assert left == []
    assert last.full
    assert last.topics == {"lab.a": 3}


async def test_a_frame_is_linked_to_the_state_and_goes_only_to_open_connections() -> None:
    publisher = FeedPublisher("lab")
    position = StagePosition(x=1, y=2, z=3)
    publisher.publish_frame("frames.camera.overview", b"nobody listens", None)
    publisher.publish({"a": 1})

    with publisher.connect_frames() as frames:
        publisher.publish_frame("frames.camera.overview", b"first", None)
        publisher.publish_frame("frames.camera.overview", b"second", position)
        message = await anext(frames)

    ((topic, value),) = message.topics.items()
    assert (topic, value.frame, value.position_um) == ("lab.frames.camera.overview", b"second", position)
    assert value.state == publisher.snapshot().cursor


async def test_close_ends_each_connection_after_its_last_message_and_refuses_new_ones() -> None:
    publisher = FeedPublisher("lab")

    with publisher.connect() as connection:
        publisher.publish({"a": 1})
        publisher.close()
        seen = [message async for message in connection]

    assert [message.topics for message in seen] == [{"lab.a": 1}]
    with pytest.raises(RuntimeError, match="closed"), publisher.connect():
        pass


async def test_a_number_that_is_not_finite_is_published_as_null_and_an_empty_frame_is_refused() -> None:
    publisher = FeedPublisher("lab")

    publisher.publish({"power": float("nan"), "limit": float("inf"), "nested": {"ok": 1.5}})

    assert publisher.snapshot().topics == {"lab.nested": {"ok": 1.5}}
    with pytest.raises(ValueError, match="at least 1 byte"):
        publisher.publish_frame("frames.camera.overview", b"", None)
