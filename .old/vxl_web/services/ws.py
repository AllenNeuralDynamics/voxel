"""WebSocket plumbing: broadcast protocol, per-client outbound queue, inbound topic router."""

import asyncio
import logging
from collections import deque
from typing import Any, Protocol

log = logging.getLogger(__name__)


# ==================== Broadcast callback protocol ====================


class BroadcastCallback(Protocol):
    """Broadcasts to all connected WS clients.

    ``with_status=True`` appends a full session-state update.
    ``exclude`` suppresses delivery to one client (usually the sender).
    """

    def __call__(
        self,
        data: dict[str, Any] | bytes,
        with_status: bool = False,
        exclude: str | None = None,
    ) -> None: ...


# ==================== Outbound: per-client priority message queue ====================

QUEUE_LIMITS: dict[int, int] = {
    0: 200,  # control messages (status, property updates, logs)
    1: 20,  # preview data (overview + tile batches)
}
DEFAULT_LIMIT = 100


class MsgQueue:
    """Per-client priority queue. Lower priority number = earlier delivery.

    Writers call ``put(msg_type, data, priority)``. The sender coroutine calls
    ``drain()``. Oldest messages are silently dropped when a level fills up.
    """

    def __init__(self) -> None:
        self._levels: dict[int, deque[tuple[str, Any]]] = {}
        self._notify = asyncio.Event()
        self.paused = False  # when True, binary preview data (priority>0) is dropped

    def _get_level(self, priority: int) -> deque[tuple[str, Any]]:
        if priority not in self._levels:
            maxlen = QUEUE_LIMITS.get(priority, DEFAULT_LIMIT)
            self._levels[priority] = deque(maxlen=maxlen)
        return self._levels[priority]

    def put(self, msg_type: str, data: Any, *, priority: int = 0) -> None:
        """Enqueue a message. Non-blocking. Paused clients drop binary (priority > 0)."""
        if self.paused and priority > 0:
            return
        self._get_level(priority).append((msg_type, data))
        self._notify.set()

    async def drain(self) -> tuple[str, Any]:
        """Pop the next message, lowest priority number first. Blocks until available."""
        while True:
            await self._notify.wait()
            for level in sorted(self._levels):
                q = self._levels[level]
                if q:
                    return q.popleft()
            self._notify.clear()


# ==================== Inbound: topic dispatch router ====================


class WsHandler(Protocol):
    """A service that handles a subset of WS topics, identified by prefix."""

    topic_prefixes: tuple[str, ...]

    async def handle_message(self, sender_id: str, topic: str, payload: dict[str, Any]) -> None: ...


class WsRouter:
    """Dispatches inbound WS messages to the first service whose prefix matches."""

    def __init__(self, handlers: list[WsHandler]) -> None:
        self._handlers = handlers

    async def dispatch(self, sender_id: str, topic: str, payload: dict[str, Any]) -> None:
        for h in self._handlers:
            if any(topic.startswith(p) for p in h.topic_prefixes):
                await h.handle_message(sender_id, topic, payload)
                return
        log.warning("Unknown topic from %s: %s", sender_id, topic)
