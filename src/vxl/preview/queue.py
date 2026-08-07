"""Latest-only scheduling for consumers of preview frame feeds."""

import asyncio
from collections import OrderedDict

from .protocol import PreviewKey


class LatestFrameQueue:
    """Async queue retaining at most one pending frame per preview key.

    Replacing a pending frame does not change its position, which prevents a
    busy stream from starving other keys already waiting to be handled.
    Producers never wait; consumers await :meth:`get`.
    """

    def __init__(self) -> None:
        self._items: OrderedDict[PreviewKey, bytes] = OrderedDict()
        self._ready = asyncio.Event()

    def put(self, key: PreviewKey, frame: bytes) -> None:
        """Insert or replace the pending frame for ``key`` without waiting."""
        self._items[key] = frame
        self._ready.set()

    async def get(self) -> tuple[PreviewKey, bytes]:
        """Wait for and remove the oldest pending key and its latest frame."""
        while not self._items:
            self._ready.clear()
            await self._ready.wait()
        return self._items.popitem(last=False)

    def clear(self) -> None:
        """Discard every pending frame."""
        self._items.clear()
        self._ready.clear()

    def __len__(self) -> int:
        return len(self._items)


__all__ = ["LatestFrameQueue"]
