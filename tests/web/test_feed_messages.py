"""Tests for the feed's messages: the merge rule and the packed frame message."""

from collections.abc import Callable
from typing import cast

import msgpack
import pytest
from pydantic import JsonValue
from vxlib.vector import StagePosition

from vxl.web.feed import FeedCursor, FeedFrame, FrameMessage, StateMessage


def _state(seq: int, topics: dict[str, JsonValue], *, full: bool = False, stream: str = "s1") -> StateMessage:
    cursor = FeedCursor(stream_id=stream, seq=seq)
    return StateMessage(cursor=cursor, sent_at_unix_us=seq * 1000, full=full, topics=topics)


def _frames(seq: int, topics: dict[str, bytes], position: StagePosition | None = None) -> FrameMessage:
    state = FeedCursor(stream_id="s1", seq=5)
    values = {topic: FeedFrame(state=state, position_um=position, frame=frame) for topic, frame in topics.items()}
    return FrameMessage(cursor=FeedCursor(stream_id="f1", seq=seq), sent_at_unix_us=seq * 1000, topics=values)


def test_a_reader_that_merges_each_message_keeps_the_newest_value_of_each_topic() -> None:
    full = _state(5, {"a": 1, "b": {"x": 1}, "c": 3}, full=True)

    kept = full.merge(_state(6, {"a": 2})).merge(_state(7, {"b": None}))

    assert kept == _state(7, {"a": 2, "c": 3}, full=True)


def test_what_waits_for_a_slow_reader_keeps_each_removal() -> None:
    waiting = _state(6, {"a": 1, "b": 1}).merge(_state(7, {"a": 2, "b": None}))

    assert waiting == _state(7, {"a": 2, "b": None})


def test_a_full_message_replaces_what_came_before_also_from_a_new_stream() -> None:
    later = _state(1, {"a": 0}, full=True, stream="s2")

    assert _state(6, {"a": 2}).merge(later) is later


@pytest.mark.parametrize("later", [_state(6, {"a": 3}), _state(9, {"a": 3}, stream="s2")])
def test_a_message_that_does_not_follow_is_refused(later: StateMessage) -> None:
    with pytest.raises(ValueError, match="does not"):
        _state(6, {"a": 2}).merge(later)


def test_a_full_message_cannot_remove_a_topic() -> None:
    with pytest.raises(ValueError, match="cannot remove a topic"):
        _state(1, {"a": None}, full=True)


def test_frames_that_wait_keep_the_newest_of_each_topic_and_pack_as_1_packet() -> None:
    position = StagePosition(x=1, y=2, z=3)

    waiting = (
        _frames(1, {"camera.overview": b"old"})
        .merge(_frames(2, {"camera.viewport": b"zoom"}))
        .merge(_frames(3, {"camera.overview": b"new"}, position))
    )
    packed = waiting.pack()

    assert [(topic, value.frame) for topic, value in waiting.topics.items()] == [
        ("camera.overview", b"new"),
        ("camera.viewport", b"zoom"),
    ]
    assert waiting.topics["camera.overview"].position_um == position
    assert packed[:5] == b"VXFP\x01"
    assert FrameMessage.from_packed(packed) == waiting


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda packed: packed[:-2], "truncated in the frame"),
        (lambda packed: packed + b"xx", "2 bytes after its last frame"),
        (lambda packed: packed[:4] + b"\x02" + packed[5:], "framing version: 2"),
        (lambda packed: b"VXLP" + packed[4:], "invalid VXFP magic"),
    ],
)
def test_bytes_that_are_not_1_whole_packet_are_refused(change: Callable[[bytes], bytes], error: str) -> None:
    packed = _frames(1, {"camera.overview": b"frame"}).pack()

    with pytest.raises(ValueError, match=error):
        FrameMessage.from_packed(change(packed))


def test_a_header_without_topics_is_refused() -> None:
    header = cast("bytes", msgpack.packb({"cursor": {"stream_id": "f1", "seq": 1}}))

    with pytest.raises(ValueError, match="invalid VXFP header"):
        FrameMessage.from_packed(b"VXFP\x01" + len(header).to_bytes(4) + header + b"x")
