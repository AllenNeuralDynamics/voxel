"""MsgBus + Client — typed pubsub over WebSocket, with per-client backpressure.

Public abstractions:
    - :class:`MsgQueue` — per-client priority queue with drop-oldest backpressure.
    - :class:`Client` — one connected WS peer; owns its WS, queue, paused state, sender task.
    - :class:`MsgBus` — app-scoped registry of clients; exposes typed pubsub.

Wire format on the WS: ``msgpack.packb([topic, body_bytes])`` — a 2-element array
that mimics ZMQ multipart on a transport that doesn't have it natively. Body
bytes are either packed Pydantic (typed events) or already-packed bytes (rigup
forwarding); the bus doesn't care which.

Subscription model:
    - **Inbound commands** — services register typed handlers via
      :meth:`MsgBus.on_command` (single handler per topic; raises on duplicate).
    - **Outbound events** — services :meth:`MsgBus.broadcast` typed Pydantic
      models or pass-through bytes; bus fans to all connected clients.
    - **Per-client controls** — pause/resume live on :class:`Client`; access via
      :meth:`MsgBus.get_client`.
"""

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, cast, overload

import msgpack
from fastapi import WebSocket
from pydantic import BaseModel
from rigup.wire import pack, unpack

from vxlib import Cell, Teardown

log = logging.getLogger(__name__)

type ClientId = str
type CommandHandler[T] = Callable[[T, ClientId], Awaitable[None]]


# ==================== Per-client priority queue ====================

QUEUE_LIMITS: dict[int, int] = {
    0: 200,  # control messages (status, property updates, logs)
    1: 20,  # preview data (overview + tile batches)
}
DEFAULT_LIMIT = 100


class MsgQueue:
    """Per-client priority queue. Lower priority number = earlier delivery.

    Writers call :meth:`put`. The sender coroutine calls :meth:`drain`.
    Oldest messages are silently dropped when a level fills up.
    """

    def __init__(self) -> None:
        self._levels: dict[int, deque[bytes]] = {}
        self._notify = asyncio.Event()

    def _get_level(self, priority: int) -> deque[bytes]:
        if priority not in self._levels:
            maxlen = QUEUE_LIMITS.get(priority, DEFAULT_LIMIT)
            self._levels[priority] = deque(maxlen=maxlen)
        return self._levels[priority]

    def put(self, msg: bytes, *, priority: int = 0) -> None:
        """Enqueue a message. Non-blocking; drops oldest when level is full."""
        self._get_level(priority).append(msg)
        self._notify.set()

    async def drain(self) -> bytes:
        """Pop the next message, lowest priority number first. Blocks until available."""
        while True:
            await self._notify.wait()
            for level in sorted(self._levels):
                q = self._levels[level]
                if q:
                    return q.popleft()
            self._notify.clear()


# ==================== Per-WS-peer client ====================


class Client:
    """One connected WS peer. Owns its connection, queue, paused state, sender task.

    Per-client concerns (buffering, priority, paused state, lifecycle) live here.
    :class:`MsgBus` just registers/deregisters clients and iterates them on
    broadcast — pause and per-client targeting go through this class.
    """

    def __init__(self, client_id: ClientId, ws: WebSocket) -> None:
        self.id = client_id
        self._ws = ws
        self._queue = MsgQueue()
        self._paused = False
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

    def enqueue(self, msg: bytes, *, priority: int = 0) -> None:
        """Queue a message for delivery. Drops priority>0 messages while paused."""
        if self._paused and priority > 0:
            return
        self._queue.put(msg, priority=priority)

    def pause(self) -> None:
        """Stop accepting priority>0 messages (e.g. preview frames). Control messages keep flowing."""
        self._paused = True

    def resume(self) -> None:
        """Resume accepting all messages."""
        self._paused = False

    @property
    def is_paused(self) -> bool:
        return self._paused

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


# ==================== MsgBus ====================


class _CommandEntry[T: BaseModel]:
    __slots__ = ("handler", "schema")

    def __init__(self, schema: type[T], handler: CommandHandler[T]) -> None:
        self.schema = schema
        self.handler = handler


class _ClientActive(BaseModel):
    """Inbound ``client.active`` control: whether this WS peer is actively viewing.

    ``False`` pauses the peer's queue (drops priority>0 payloads — frames/tiles — while still delivering
    status); ``True`` resumes. Lets a backgrounded tab stop its own frame delivery without affecting any
    other client or global state."""

    active: bool


class MsgBus:
    """App-scoped wire bus: WS connection registry + typed pubsub.

    Owns the set of connected :class:`Client` instances. Routes inbound commands
    to typed handlers (Pydantic-validated, single handler per topic). Broadcasts
    outbound events as packed Pydantic models or pass-through bytes.

    Domain-agnostic: knows topics, schemas, callbacks, clients. Does not know
    devices, preview, sessions, etc. — services layer those on by registering
    command handlers and calling broadcast.

    The :attr:`clients` Cell is reactive — services that care about connection
    state (e.g. "stop preview when last client disconnects") subscribe to it
    instead of registering a separate connect/disconnect hook.
    """

    def __init__(self) -> None:
        self._clients: dict[ClientId, Client] = {}
        self._handlers: dict[str, _CommandEntry[Any]] = {}
        self.clients: Cell[set[ClientId]] = Cell(set())
        self._log = log
        self.on_command("client.active", _ClientActive, self._set_client_active)  # built-in per-client backpressure

    # ---- Connection lifecycle (called by the WS endpoint) ----

    async def add_client(self, client: Client) -> None:
        """Register a started Client. Updates the reactive ``clients`` Cell."""
        self._clients[client.id] = client
        await self.clients.set(set(self._clients.keys()))

    async def remove_client(self, client: Client) -> None:
        """Deregister and close a Client. Updates the reactive ``clients`` Cell."""
        self._clients.pop(client.id, None)
        await client.close()
        await self.clients.set(set(self._clients.keys()))

    def get_client(self, client_id: ClientId) -> Client | None:
        """Look up a connected client (e.g. for pause/resume)."""
        return self._clients.get(client_id)

    async def _set_client_active(self, cmd: _ClientActive, client_id: ClientId) -> None:
        """Pause/resume a peer's own queue on ``client.active`` (e.g. tab backgrounded)."""
        client = self.get_client(client_id)
        if client is None:
            return
        if cmd.active:
            client.resume()
        else:
            client.pause()

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

    # ---- Outbound — broadcast events (typed or pass-through bytes) ----

    @overload
    def broadcast(self, topic: str, body: bytes, *, exclude: ClientId | None = None) -> None: ...

    @overload
    def broadcast(self, topic: str, body: BaseModel, *, exclude: ClientId | None = None) -> None: ...

    def broadcast(self, topic: str, body: BaseModel | bytes, *, exclude: ClientId | None = None) -> None:
        """Send an event to all connected clients, optionally excluding one.

        Bytes pass through verbatim at priority 1; typed bodies are packed
        and sent at priority 0.
        """
        body_bytes = body if isinstance(body, bytes) else pack(body)
        # msgpack stubs declare `bytes | None`; for valid input it always returns bytes.
        msg = cast("bytes", msgpack.packb([topic, body_bytes]))
        priority = 1 if isinstance(body, bytes) else 0
        for cid, client in self._clients.items():
            if cid == exclude:
                continue
            client.enqueue(msg, priority=priority)
