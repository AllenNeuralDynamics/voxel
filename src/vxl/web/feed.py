"""The feed: the messages that a service publishes, its server passes on and a window reads, and the sending end that
gives them to each reader in order.

A feed topic is a dotted name under its publisher's prefix, such as ``stations.<id>.instrument.devices.camera``. It
is not a rigup device topic, such as ``live`` or ``props.update``.
"""

import asyncio
import math
import time
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from struct import Struct
from typing import Protocol, Self, cast

import msgpack
from pydantic import Field, JsonValue, model_validator
from vxlib.schema import FrozenModel
from vxlib.vector import StagePosition

_MAGIC = b"VXFP"
_FRAMING_VERSION = 1
_PREFIX = Struct(">4sBI")
"""The start of a packed frame message: the magic, the framing version, and the length of the header."""

_MAX_HEADER_BYTES = 64 * 1024


class FeedCursor(FrozenModel):
    """A place in 1 ordered stream of messages. Within a ``stream_id``, ``seq`` only goes up."""

    stream_id: str = Field(min_length=1)
    seq: int = Field(ge=0)

    def check_follows(self, earlier: Self) -> None:
        """Raise :class:`ValueError` unless this cursor comes after ``earlier`` in the same stream."""
        if self.stream_id != earlier.stream_id:
            raise ValueError(f"stream {self.stream_id} does not continue stream {earlier.stream_id}")
        if self.seq <= earlier.seq:
            raise ValueError(f"message {self.seq} does not come after message {earlier.seq}")


class StateMessage(FrozenModel):
    """A message on the state socket. ``topics`` holds each topic that changed with its new value; ``None`` removes
    the topic. A ``full`` message holds every topic, and its reader starts over from it."""

    cursor: FeedCursor
    sent_at_unix_us: int = Field(ge=0)
    full: bool = False
    topics: dict[str, JsonValue]

    @model_validator(mode="after")
    def _a_full_message_removes_nothing(self) -> Self:
        if self.full and any(value is None for value in self.topics.values()):
            raise ValueError("a full message cannot remove a topic")
        return self

    def merge(self, later: Self) -> Self:
        """This message with ``later`` applied: the newest value of each topic, at the cursor of ``later``. A full
        ``later`` replaces this message. Raise :class:`ValueError` when a ``later`` that is not full does not come
        after this message in the same stream."""
        if later.full:
            return later
        later.cursor.check_follows(self.cursor)
        topics = {**self.topics, **later.topics}
        if self.full:
            topics = {topic: value for topic, value in topics.items() if value is not None}
        return self.model_copy(
            update={"cursor": later.cursor, "sent_at_unix_us": later.sent_at_unix_us, "topics": topics}
        )


class FeedFrame(FrozenModel):
    """The value of a frame topic: 1 camera frame as packed VXSF bytes, unopened, the state cursor it belongs to, and
    the stage position for it. ``position_um`` is ``None`` when the stage position is unknown."""

    state: FeedCursor
    position_um: StagePosition | None = None
    frame: bytes = Field(min_length=1)


class FrameMessage(FrozenModel):
    """A message on the frame socket: the newest frame of each topic in it. It usually holds 1 topic, and more only
    when frames waited for a slow reader."""

    cursor: FeedCursor
    sent_at_unix_us: int = Field(ge=0)
    topics: dict[str, FeedFrame] = Field(min_length=1)

    def merge(self, later: Self) -> Self:
        """This message with ``later`` applied: the newest frame of each topic, at the cursor of ``later``. Raise
        :class:`ValueError` when ``later`` does not come after this message in the same stream."""
        later.cursor.check_follows(self.cursor)
        return self.model_copy(
            update={
                "cursor": later.cursor,
                "sent_at_unix_us": later.sent_at_unix_us,
                "topics": {**self.topics, **later.topics},
            }
        )

    def pack(self) -> bytes:
        """Serialize as a VXFP packet: the prefix, a MessagePack header, then each topic's frame in the
        order of the header's topics."""
        header = {
            "cursor": self.cursor.model_dump(),
            "sent_at_unix_us": self.sent_at_unix_us,
            "topics": {
                topic: {
                    "state": value.state.model_dump(),
                    "position_um": value.position_um and value.position_um.model_dump(),
                    "frame_byte_length": len(value.frame),
                }
                for topic, value in self.topics.items()
            },
        }
        packed = cast("bytes", msgpack.packb(header, use_bin_type=True))
        if len(packed) > _MAX_HEADER_BYTES:
            raise ValueError(f"VXFP header is too large: {len(packed)} bytes")
        frames = b"".join(value.frame for value in self.topics.values())
        return _PREFIX.pack(_MAGIC, _FRAMING_VERSION, len(packed)) + packed + frames

    @classmethod
    def from_packed(cls, packed: bytes | bytearray | memoryview) -> Self:
        """Parse a VXFP packet, leaving each VXSF frame unopened. Raise :class:`ValueError` when the bytes
        are not 1 whole packet of that version."""
        packet = memoryview(packed)
        if len(packet) < _PREFIX.size:
            raise ValueError("VXFP packet is truncated before its prefix")
        magic, version, header_length = _PREFIX.unpack_from(packet)
        if magic != _MAGIC:
            raise ValueError("invalid VXFP magic")
        if version != _FRAMING_VERSION:
            raise ValueError(f"unsupported VXFP framing version: {version}")
        if not 0 < header_length <= _MAX_HEADER_BYTES:
            raise ValueError(f"invalid VXFP header length: {header_length}")

        offset = _PREFIX.size + header_length
        try:
            header = msgpack.unpackb(packet[_PREFIX.size : offset], raw=False)
            topics: dict[str, FeedFrame] = {}
            for topic, entry in header["topics"].items():
                frame = bytes(packet[offset : offset + entry["frame_byte_length"]])
                if len(frame) != entry["frame_byte_length"]:
                    raise ValueError(f"VXFP packet is truncated in the frame of {topic}")
                topics[topic] = FeedFrame(state=entry["state"], position_um=entry["position_um"], frame=frame)
                offset += len(frame)
            message = cls(cursor=header["cursor"], sent_at_unix_us=header["sent_at_unix_us"], topics=topics)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("invalid VXFP header") from error
        if offset != len(packet):
            raise ValueError(f"VXFP packet has {len(packet) - offset} bytes after its last frame")
        return message


class _Message(Protocol):
    """What the 2 kinds of message share for a reader: a place in their stream, and the merge rule."""

    @property
    def cursor(self) -> FeedCursor: ...

    def merge(self, later: Self) -> Self: ...


class _Waiting[M: _Message]:
    """What waits for 1 reader: at most 1 message, merged from every message since the reader last took one."""

    def __init__(self, message: M | None = None) -> None:
        self._message = message
        self._ended = False
        self._ready = asyncio.Event()

    def offer(self, message: M) -> None:
        if self._message is None or self._message.cursor.stream_id != message.cursor.stream_id:
            self._message = message  # what waits from an older stream is of no use to the reader
        else:
            self._message = self._message.merge(message)
        self._ready.set()

    def clear(self) -> None:
        self._message = None

    def end(self) -> None:
        self._ended = True
        self._ready.set()

    async def take(self) -> M:
        while self._message is None:
            if self._ended:
                raise StopAsyncIteration
            self._ready.clear()
            await self._ready.wait()
        message, self._message = self._message, None
        return message


class FeedConnection[M: _Message]:
    """The messages of 1 service for 1 reader, in order. Iteration ends when the sending end closes, after the last
    message. A slow reader misses no topic: what waits for it is merged into 1 message, with the newest value of each
    topic."""

    def __init__(self, waiting: _Waiting[M]) -> None:
        self._waiting = waiting

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> M:
        return await self._waiting.take()


class FeedRelay:
    """Gives each message of 1 service to every connection, unchanged, with no transport of its own. It keeps the last
    value of each state topic, so a new connection starts with 1 full message. Frames are not kept: a connection gets
    the frames sent while it is open, the newest of each topic."""

    def __init__(self) -> None:
        self._state = StateMessage(
            cursor=FeedCursor(stream_id=uuid.uuid4().hex, seq=0), sent_at_unix_us=self._now_us(), full=True, topics={}
        )
        self._frames_at: FeedCursor | None = None
        self._state_readers: set[_Waiting[StateMessage]] = set()
        self._frame_readers: set[_Waiting[FrameMessage]] = set()
        self._closed = False

    @property
    def closed(self) -> bool:
        """Whether :meth:`close` ran: no new connection is accepted."""
        return self._closed

    def snapshot(self) -> StateMessage:
        """Every state topic as of now, as 1 full message."""
        return self._state

    def send(self, message: StateMessage) -> None:
        """Give a state message to every state connection. A full message replaces every topic kept, and drops the
        frames that wait."""
        self._state = self._state.merge(message)
        for reader in self._state_readers:
            reader.offer(message)
        if message.full:
            for waiting in self._frame_readers:
                waiting.clear()

    def send_frames(self, message: FrameMessage) -> None:
        """Give a frame message to every frame connection. Raise :class:`ValueError`, and give it to none, when it does
        not come after the last one of its stream."""
        if self._frames_at is not None and self._frames_at.stream_id == message.cursor.stream_id:
            message.cursor.check_follows(self._frames_at)
        self._frames_at = message.cursor
        for reader in self._frame_readers:
            reader.offer(message)

    @contextmanager
    def connect(self) -> Generator[FeedConnection[StateMessage]]:
        """A connection to the state topics. Its first message is full."""
        with self._reader(self._state_readers, _Waiting(self._state)) as connection:
            yield connection

    @contextmanager
    def connect_frames(self) -> Generator[FeedConnection[FrameMessage]]:
        """A connection to the frame topics."""
        with self._reader(self._frame_readers, _Waiting[FrameMessage]()) as connection:
            yield connection

    def close(self) -> None:
        """End every connection after the message that waits for it, and accept no more."""
        self._closed = True
        for reader in (*self._state_readers, *self._frame_readers):
            reader.end()

    @contextmanager
    def _reader[M: _Message](self, readers: set[_Waiting[M]], waiting: _Waiting[M]) -> Generator[FeedConnection[M]]:
        if self._closed:
            raise RuntimeError("the feed is closed")
        readers.add(waiting)
        try:
            yield FeedConnection(waiting)
        finally:
            readers.discard(waiting)
            waiting.end()

    @staticmethod
    def _now_us() -> int:
        return time.time_ns() // 1_000


class FeedPublisher(FeedRelay):
    """Makes the messages of 1 service from its topics and gives them to every connection. Every topic gets ``prefix``
    in front, such as ``stations.<id>``."""

    def __init__(self, prefix: str) -> None:
        super().__init__()
        self._prefix = prefix
        self._frame_cursor = FeedCursor(stream_id=uuid.uuid4().hex, seq=0)

    def publish(self, topics: Mapping[str, JsonValue]) -> None:
        """Send the topics that changed, each with its new value. ``None`` removes a topic, and so does a number that
        JSON cannot hold (NaN or an infinity)."""
        if topics:
            self._publish(full=False, topics={self._name(topic): self._held(value) for topic, value in topics.items()})

    def replace(self, topics: Mapping[str, JsonValue]) -> None:
        """Send every topic as 1 full message, from which each reader starts over. Frames that wait are dropped."""
        held = {self._name(topic): self._held(value) for topic, value in topics.items()}
        self._publish(full=True, topics={topic: value for topic, value in held.items() if value is not None})

    def publish_frame(self, topic: str, frame: bytes, position_um: StagePosition | None) -> None:
        """Send 1 camera frame, as packed VXSF bytes, linked to the state as of now. Raise :class:`ValueError` for a
        frame with no bytes."""
        if not frame:
            raise ValueError("a frame holds at least 1 byte")
        if not self._frame_readers:
            return
        self._frame_cursor = self._frame_cursor.model_copy(update={"seq": self._frame_cursor.seq + 1})
        value = FeedFrame(state=self._state.cursor, position_um=position_um, frame=frame)
        self.send_frames(
            FrameMessage(cursor=self._frame_cursor, sent_at_unix_us=self._now_us(), topics={self._name(topic): value})
        )

    def _name(self, topic: str) -> str:
        return f"{self._prefix}.{topic}"

    @staticmethod
    def _held(value: JsonValue) -> JsonValue:
        """``value``, or ``None`` for a number that JSON cannot hold: it would be written as ``null``, which removes
        the topic at a reader, and which a reader refuses in a full message."""
        return None if isinstance(value, float) and not math.isfinite(value) else value

    def _publish(self, *, full: bool, topics: dict[str, JsonValue]) -> None:
        # Built without validation: the values are JSON already, and checking a large one again costs milliseconds.
        self.send(
            StateMessage.model_construct(
                cursor=self._state.cursor.model_copy(update={"seq": self._state.cursor.seq + 1}),
                sent_at_unix_us=self._now_us(),
                full=full,
                topics=topics,
            )
        )


__all__ = [
    "FeedConnection",
    "FeedCursor",
    "FeedFrame",
    "FeedPublisher",
    "FeedRelay",
    "FrameMessage",
    "StateMessage",
]
