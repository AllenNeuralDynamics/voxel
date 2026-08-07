"""Outbound ZeroMQ publishers for instrument state and preview frames.

Both publishers connect outward with DEALER sockets so a microscope can sit
behind NAT or a firewall while an external service binds the stable endpoint.
Instrument callbacks only update bounded in-memory queues; all network I/O is
performed by background tasks.
"""

import asyncio
from collections import deque
from contextlib import suppress
from typing import TYPE_CHECKING, Any, cast

import msgpack
import zmq
import zmq.asyncio

from vxl.preview.protocol import PreviewEmission
from vxl.preview.queue import LatestFrameQueue

from .feed import InstrumentFeed, InstrumentUpdate, InstrumentView

if TYPE_CHECKING:
    from vxlib import Teardown

_PROTOCOL_VERSION = 1
_DEFAULT_FEED_QUEUE_SIZE = 1_024
_DEFAULT_FEED_SEND_HWM = 16
_DEFAULT_PREVIEW_SEND_HWM = 1


def _pack(value: Any) -> bytes:
    return cast("bytes", msgpack.packb(value, use_bin_type=True))


def _validate_source_id(source_id: str) -> bytes:
    encoded = source_id.encode()
    if not encoded or len(encoded) > 255:
        raise ValueError("source_id must encode to between 1 and 255 bytes")
    return encoded


def _dealer(context: zmq.asyncio.Context, endpoint: str, source_id: str, *, send_hwm: int) -> zmq.asyncio.Socket:
    if not endpoint:
        raise ValueError("endpoint must not be empty")
    if send_hwm < 1:
        raise ValueError("send_hwm must be positive")

    socket = context.socket(zmq.DEALER)
    socket.setsockopt(zmq.IDENTITY, _validate_source_id(source_id))
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.IMMEDIATE, 1)
    socket.setsockopt(zmq.SNDHWM, send_hwm)
    if endpoint.startswith("tcp://"):
        socket.setsockopt(zmq.TCP_KEEPALIVE, 1)
        socket.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 1)
        socket.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 1)
        socket.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)
    socket.connect(endpoint)
    return socket


def _hello(source_id: str, stream: str) -> bytes:
    return _pack({"protocol_version": _PROTOCOL_VERSION, "source_id": source_id, "stream": stream})


class StatusPub:
    """Publish one opened :class:`InstrumentFeed` status lane to an external service.

    Updates remain ordered. If the bounded pending-update queue fills, its
    deltas are replaced by a fresh cached view, allowing the receiver to resume
    from that view's cursor without querying any devices.
    """

    def __init__(
        self,
        endpoint: str,
        source_id: str,
        *,
        context: zmq.asyncio.Context | None = None,
        max_pending_updates: int = _DEFAULT_FEED_QUEUE_SIZE,
        send_hwm: int = _DEFAULT_FEED_SEND_HWM,
    ) -> None:
        if max_pending_updates < 1:
            raise ValueError("max_pending_updates must be positive")
        self._endpoint = endpoint
        self._source_id = source_id
        self._context = context or zmq.asyncio.Context.instance()
        self._max_pending_updates = max_pending_updates
        self._send_hwm = send_hwm
        self._feed: InstrumentFeed | None = None
        self._socket: zmq.asyncio.Socket | None = None
        self._task: asyncio.Task[None] | None = None
        self._unsub: Teardown | None = None
        self._wake = asyncio.Event()
        self._pending_view: InstrumentView | None = None
        self._pending_updates: deque[InstrumentUpdate] = deque()

    @property
    def is_open(self) -> bool:
        """Whether the publisher is subscribed and its sender task is running."""
        return self._task is not None

    async def open(self, feed: InstrumentFeed) -> None:
        """Subscribe to an opened feed and start publishing it."""
        if self.is_open:
            raise RuntimeError("feed publisher is already open")
        if not feed.is_open:
            raise RuntimeError("instrument feed must be open before its publisher")

        socket = _dealer(
            self._context,
            self._endpoint,
            self._source_id,
            send_hwm=self._send_hwm,
        )
        self._feed = feed
        self._socket = socket
        self._pending_view = feed.view()
        self._unsub = feed.updates.subscribe(self._on_update)
        self._wake.set()
        self._task = asyncio.create_task(self._send_loop(socket), name="instrument-feed-pub")

    async def close(self) -> None:
        """Stop publishing and release the socket. Idempotent."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._socket is not None:
            self._socket.close(linger=0)
            self._socket = None
        self._feed = None
        self._pending_view = None
        self._pending_updates.clear()
        self._wake.clear()

    def _on_update(self, update: InstrumentUpdate) -> None:
        feed = self._feed
        if feed is None:
            return
        if len(self._pending_updates) >= self._max_pending_updates:
            self._pending_updates.clear()
            self._pending_view = feed.view()
        else:
            self._pending_updates.append(update)
        self._wake.set()

    async def _send_loop(self, socket: zmq.asyncio.Socket) -> None:
        await socket.send_multipart([b"hello", _hello(self._source_id, "feed")])
        while True:
            await self._wake.wait()
            while message := self._next_message():
                await socket.send_multipart(message)
            self._wake.clear()

    def _next_message(self) -> list[bytes] | None:
        if self._pending_view is not None:
            view = self._pending_view
            self._pending_view = None
            return [b"view", _pack(view.model_dump(mode="json"))]
        if self._pending_updates:
            return [b"update", _pack(self._pending_updates.popleft().wire_dict())]
        return None


class PreviewPub:
    """Publish already-encoded preview packets to an external service.

    At most one unsent packet is retained per channel and layer. A newer packet
    for the same key replaces the older one while the network sender is busy.
    """

    def __init__(
        self,
        endpoint: str,
        source_id: str,
        *,
        context: zmq.asyncio.Context | None = None,
        send_hwm: int = _DEFAULT_PREVIEW_SEND_HWM,
    ) -> None:
        self._endpoint = endpoint
        self._source_id = source_id
        self._context = context or zmq.asyncio.Context.instance()
        self._send_hwm = send_hwm
        self._socket: zmq.asyncio.Socket | None = None
        self._task: asyncio.Task[None] | None = None
        self._unsubs: list[Teardown] = []
        self._pending = LatestFrameQueue()

    @property
    def is_open(self) -> bool:
        """Whether the publisher is subscribed and its sender task is running."""
        return self._task is not None

    async def open(self, feed: InstrumentFeed) -> None:
        """Subscribe to preview packets and start publishing them."""
        if self.is_open:
            raise RuntimeError("preview publisher is already open")

        socket = _dealer(
            self._context,
            self._endpoint,
            self._source_id,
            send_hwm=self._send_hwm,
        )
        self._socket = socket
        self._unsubs = [
            feed.frames.subscribe(self._on_frame),
            feed.delivery_stream_id.subscribe(lambda _stream_id: self._pending.clear()),
        ]
        self._task = asyncio.create_task(self._send_loop(socket), name="preview-pub")

    async def close(self) -> None:
        """Stop publishing and release the socket. Idempotent."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._socket is not None:
            self._socket.close(linger=0)
            self._socket = None
        self._pending.clear()

    def _on_frame(self, update: PreviewEmission) -> None:
        channel_id, layer, packet = update
        self._pending.put((channel_id, layer), packet)

    async def _send_loop(self, socket: zmq.asyncio.Socket) -> None:
        await socket.send_multipart([b"hello", _hello(self._source_id, "preview")])
        while True:
            _key, packet = await self._pending.get()
            await socket.send_multipart([b"frame", packet])


__all__ = ["PreviewPub", "StatusPub"]
