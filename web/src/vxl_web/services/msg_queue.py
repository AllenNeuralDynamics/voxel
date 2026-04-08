"""Priority message queue for WebSocket clients.

Messages with lower priority numbers are sent first. Typical usage:
- priority=0: control messages (status, logs, errors) — always first
- priority=1: preview data (overview + tiles batch) — after control

Each priority level has a bounded deque. Oldest messages are silently dropped
when full, preventing unbounded accumulation if the sender can't keep up.
"""

import asyncio
from collections import deque
from typing import Any

# Default maxlen per priority level
QUEUE_LIMITS: dict[int, int] = {
    0: 200,  # control messages (status, property updates, logs)
    1: 20,  # preview data (overview + tile batches)
}

DEFAULT_LIMIT = 100


class MsgQueue:
    """Per-client priority message queue.

    Writers call put(msg_type, data, priority).
    The sender coroutine calls drain() to get the next item, lowest priority number first.
    """

    def __init__(self) -> None:
        self._levels: dict[int, deque[tuple[str, Any]]] = {}
        self._notify = asyncio.Event()
        self.paused = False  # when True, binary preview data is not enqueued

    def _get_level(self, priority: int) -> deque[tuple[str, Any]]:
        if priority not in self._levels:
            maxlen = QUEUE_LIMITS.get(priority, DEFAULT_LIMIT)
            self._levels[priority] = deque(maxlen=maxlen)
        return self._levels[priority]

    def put(self, msg_type: str, data: Any, *, priority: int = 0) -> None:
        """Enqueue a message. Oldest dropped if full. Non-blocking.

        When paused, binary messages (priority > 0) are silently discarded.
        Control messages (priority 0) always get through.
        """
        if self.paused and priority > 0:
            return
        self._get_level(priority).append((msg_type, data))
        self._notify.set()

    async def drain(self) -> tuple[str, Any]:
        """Return the next message, lowest priority number first. Blocks until available."""
        while True:
            await self._notify.wait()

            for level in sorted(self._levels):
                q = self._levels[level]
                if q:
                    return q.popleft()

            self._notify.clear()
