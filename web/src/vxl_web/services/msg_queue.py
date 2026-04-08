"""Priority message queue for WebSocket clients.

Messages with lower priority numbers are sent first. Typical usage:
- priority=0: control messages (status, logs, errors) — always first
- priority=1: preview data (overview + tiles batch) — after control
"""

import asyncio
from collections import defaultdict, deque
from typing import Any


class MsgQueue:
    """Per-client priority message queue.

    Writers call put(msg_type, data, priority).
    The sender coroutine calls drain() to get the next item, highest priority first.
    """

    def __init__(self) -> None:
        self._levels: dict[int, deque[tuple[str, Any]]] = defaultdict(deque)
        self._notify = asyncio.Event()

    def put(self, msg_type: str, data: Any, *, priority: int = 0) -> None:
        """Enqueue a message at the given priority level. Non-blocking."""
        self._levels[priority].append((msg_type, data))
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
