"""Primary control and dedicated preview WebSocket transports.

Public abstractions:
    - :class:`MsgBus` — typed topic pubsub over the primary control WebSocket.
    - :class:`PreviewBus` — opaque latest-only packets over the preview WebSocket.

The primary wire format is ``msgpack.packb([topic, body_bytes])``. The dedicated
preview socket sends one complete opaque VXPD packet per binary message.
"""

import asyncio
import logging
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, cast

import msgpack
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from rigup.wire import pack, unpack

from vxl.instrument import Instrument
from vxl.preview import LatestFrameQueue, PreviewEmission, PreviewKey
from vxlib import Teardown

log = logging.getLogger(__name__)

__all__ = ["MsgBus", "PreviewBus"]

type ClientId = str
type CommandHandler[T] = Callable[[T, ClientId], Awaitable[None]]

PREVIEW_DISCONNECT_GRACE_SECONDS = 2.0


class _MsgQueue:
    """Bounded FIFO that silently drops the oldest message when full."""

    QUEUE_LIMIT = 200

    def __init__(self) -> None:
        self._messages: deque[bytes] = deque(maxlen=self.QUEUE_LIMIT)
        self._notify = asyncio.Event()

    def put(self, msg: bytes) -> None:
        """Enqueue a message. Non-blocking; drops the oldest when the queue is full."""
        self._messages.append(msg)
        self._notify.set()

    async def drain(self) -> bytes:
        """Pop the oldest message, blocking until one is available."""
        while not self._messages:
            self._notify.clear()
            await self._notify.wait()
        return self._messages.popleft()


class _MsgClient:
    """One connected WS peer. Owns its connection, queue, and sender task.

    Per-client buffering and lifecycle live here. :class:`MsgBus` just
    registers/deregisters clients and iterates them on broadcast.
    """

    def __init__(self, client_id: ClientId, ws: WebSocket) -> None:
        self.id = client_id
        self._ws = ws
        self._queue = _MsgQueue()
        self._sender_task: asyncio.Task[None] | None = None
        self._log = logging.getLogger(f"{__name__}.Client[{client_id}]")

    async def start(self) -> None:
        """Spawn the sender coroutine that drains the queue and writes to the WS."""
        self._sender_task = asyncio.create_task(self._send_loop(), name=f"client-send-{self.id}")

    async def close(self) -> None:
        """Cancel the sender and close the WS. Safe to call multiple times."""
        if self._sender_task is not None:
            self._sender_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._sender_task
            self._sender_task = None
        with suppress(Exception):
            await self._ws.close()

    def enqueue(self, msg: bytes) -> None:
        """Queue a message for delivery without blocking the broadcaster."""
        self._queue.put(msg)

    async def _send_loop(self) -> None:
        """Drain the queue and send to the WS. Cancels on close()."""
        try:
            while True:
                msg = await self._queue.drain()
                with suppress(Exception):
                    await self._ws.send_bytes(msg)
        except asyncio.CancelledError:
            return
        except Exception:
            self._log.exception("sender loop crashed")


class _CommandEntry[T: BaseModel]:
    __slots__ = ("handler", "schema")

    def __init__(self, schema: type[T], handler: CommandHandler[T]) -> None:
        self.schema = schema
        self.handler = handler


class MsgBus:
    """App-scoped wire bus: WS connection registry + typed pubsub.

    Owns the set of connected :class:`_MsgClient` instances. Routes inbound commands
    to typed handlers (Pydantic-validated, single handler per topic). Broadcasts
    outbound events as packed Pydantic models.

    Domain-agnostic: knows topics, schemas, callbacks, clients. Does not know
    devices, preview, sessions, etc. — services layer those on by registering
    command handlers and calling broadcast.

    """

    def __init__(self) -> None:
        self._clients: dict[ClientId, _MsgClient] = {}
        self._handlers: dict[str, _CommandEntry[Any]] = {}
        self._log = log

    async def close(self) -> None:
        """Close every connected peer and discard registered command handlers."""
        clients = tuple(self._clients.values())
        self._clients.clear()
        self._handlers.clear()
        await asyncio.gather(*(client.close() for client in clients))

    async def serve(self, websocket: WebSocket) -> None:
        """Accept and retain one primary peer until it disconnects."""
        await websocket.accept()
        client_id = str(uuid.uuid4())
        client = _MsgClient(client_id, websocket)
        await client.start()
        self._clients[client.id] = client
        try:
            while True:
                await self.dispatch_inbound(client_id, await websocket.receive_bytes())
        except WebSocketDisconnect:
            self._log.debug("client %s disconnected", client_id)
        finally:
            self._clients.pop(client.id, None)
            await client.close()

    # ---- Inbound — typed command handler registration ----

    def on_command[T: BaseModel](self, topic: str, schema: type[T], handler: CommandHandler[T]) -> Teardown:
        """Register the typed command handler for ``topic``.

        One handler per topic — raises ``ValueError`` if a handler already exists.
        Returns a ``Teardown`` callable to remove the registration.
        """
        if topic in self._handlers:
            raise ValueError(f"command handler already registered for topic {topic!r}")
        self._handlers[topic] = _CommandEntry(schema, handler)

        def unsub() -> None:
            self._handlers.pop(topic, None)

        return unsub

    async def dispatch_inbound(self, client_id: ClientId, raw: bytes) -> None:
        """Decode ``[topic, body]`` envelope and dispatch to the registered handler."""
        try:
            decoded = msgpack.unpackb(raw)
        except Exception:
            self._log.warning("malformed inbound message from %s", client_id)
            return

        if not (isinstance(decoded, list) and len(decoded) == 2):
            self._log.warning("inbound from %s missing [topic, body] shape", client_id)
            return

        topic, body_bytes = decoded
        if not isinstance(topic, str) or not isinstance(body_bytes, bytes):
            self._log.warning("inbound from %s has wrong types in envelope", client_id)
            return

        entry = self._handlers.get(topic)
        if entry is None:
            self._log.warning("no handler for topic %r from %s", topic, client_id)
            return

        try:
            cmd = entry.schema.model_validate(unpack(body_bytes))
        except Exception:
            self._log.exception("validation failed for topic %r from %s", topic, client_id)
            return

        try:
            await entry.handler(cmd, client_id)
        except Exception:
            self._log.exception("handler error for topic %r from %s", topic, client_id)

    # ---- Outbound — typed events ----

    def broadcast(
        self,
        topic: str,
        body: BaseModel,
        *,
        exclude: ClientId | None = None,
        exclude_unset: bool = False,
    ) -> None:
        """Send a typed event to all connected clients, optionally excluding one or unset model fields."""
        body_bytes = pack(body, exclude_unset=exclude_unset)
        # msgpack stubs declare `bytes | None`; for valid input it always returns bytes.
        msg = cast("bytes", msgpack.packb([topic, body_bytes]))
        for cid, client in self._clients.items():
            if cid == exclude:
                continue
            client.enqueue(msg)


class _PreviewClient:
    """One preview peer with independent latest-only backpressure."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._queue = LatestFrameQueue()

    def publish(self, key: PreviewKey, frame: bytes) -> None:
        self._queue.put(key, frame)

    def clear_pending(self) -> None:
        self._queue.clear()

    async def serve(self) -> None:
        sender = asyncio.create_task(self._send(), name="preview-send")
        receiver = asyncio.create_task(self._receive(), name="preview-receive")
        done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()

    async def close(self) -> None:
        with suppress(Exception):
            await self._websocket.close()

    async def _send(self) -> None:
        while True:
            _key, frame = await self._queue.get()
            await self._websocket.send_bytes(frame)

    async def _receive(self) -> None:
        while True:
            if (await self._websocket.receive())["type"] == "websocket.disconnect":
                return


class PreviewBus:
    """Follow the active Instrument and fan opaque preview packets out to WebSocket clients."""

    def __init__(self) -> None:
        self._clients: set[_PreviewClient] = set()
        self._instrument: Instrument | None = None
        self._disconnect_stop_task: asyncio.Task[None] | None = None
        self._instrument_unsubs: list[Teardown] = []

    async def close(self) -> None:
        """Detach from the instrument and close connected preview peers."""
        self.set_instrument(None)
        clients = tuple(self._clients)
        self._clients.clear()
        await asyncio.gather(*(client.close() for client in clients))

    def set_instrument(self, instrument: Instrument | None) -> None:
        """Follow one instrument's preview frames, or detach when ``None``."""
        self._cancel_disconnect_stop()
        for unsub in self._instrument_unsubs:
            unsub()
        self._instrument_unsubs = []
        self._instrument = instrument
        self._clear_pending()
        if instrument is None:
            return
        self._instrument_unsubs = [
            instrument.feed.frames.subscribe(self.publish),
            instrument.feed.delivery_stream_id.subscribe(lambda _stream_id: self._clear_pending()),
        ]

    async def serve(self, websocket: WebSocket) -> None:
        """Accept and retain one peer until either side disconnects."""
        await websocket.accept()
        self._cancel_disconnect_stop()
        client = _PreviewClient(websocket)
        self._clients.add(client)
        try:
            await client.serve()
        except (RuntimeError, WebSocketDisconnect):
            pass
        finally:
            self._clients.discard(client)
            await client.close()
            if not self._clients:
                self._schedule_disconnect_stop()

    def publish(self, item: PreviewEmission) -> None:
        """Offer an opaque packet to every client without waiting for network delivery."""
        channel_id, layer, frame = item
        key = (channel_id, layer)
        for client in tuple(self._clients):
            client.publish(key, frame)

    def _clear_pending(self) -> None:
        for client in tuple(self._clients):
            client.clear_pending()

    def _schedule_disconnect_stop(self) -> None:
        instrument = self._instrument
        if instrument is None or self._clients or self._disconnect_stop_task is not None:
            return
        self._disconnect_stop_task = asyncio.create_task(
            self._stop_unobserved_preview(instrument),
            name="preview-stop-after-disconnect",
        )

    def _cancel_disconnect_stop(self) -> None:
        if self._disconnect_stop_task is None:
            return
        task, self._disconnect_stop_task = self._disconnect_stop_task, None
        task.cancel()

    async def _stop_unobserved_preview(self, instrument: Instrument) -> None:
        current = asyncio.current_task()
        try:
            await asyncio.sleep(PREVIEW_DISCONNECT_GRACE_SECONDS)
            if self._clients or self._instrument is not instrument:
                return
            # Once the grace period expires, let shutdown finish even if a client connects concurrently.
            # Instrument.stop_preview() is a safe no-op while idle or acquiring.
            if self._disconnect_stop_task is current:
                self._disconnect_stop_task = None
            await instrument.stop_preview()
        except Exception:
            log.exception("Failed to stop preview after the last client disconnected")
        finally:
            if self._disconnect_stop_task is current:
                self._disconnect_stop_task = None
