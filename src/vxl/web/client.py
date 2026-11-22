"""A reader of the feed of 1 service, from the service itself or from its server."""

from collections.abc import AsyncGenerator

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from vxl.web.feed import FrameMessage, StateMessage


class FeedClient:
    """Reads the feed at ``url``, the address of 1 service, such as ``ws://host:8000/api/stations/<id>``. Each stream
    connects again by itself when its connection ends, for as long as the caller reads it. With ``reconnect`` false,
    each stream reads 1 connection: it ends when the connection closes, and raises when it fails."""

    def __init__(self, url: str, *, reconnect: bool = True) -> None:
        self._url = url.rstrip("/")
        self._reconnect = reconnect

    async def state(self) -> AsyncGenerator[StateMessage]:
        """Each state message. The first one of every connection is full, and its reader starts over from it."""
        async for data in self._messages("state"):
            yield StateMessage.model_validate_json(data)

    async def frames(self) -> AsyncGenerator[FrameMessage]:
        """Each frame message, sent while this reader is connected."""
        async for data in self._messages("frames"):
            if isinstance(data, bytes):
                yield FrameMessage.from_packed(data)

    async def _messages(self, socket: str) -> AsyncGenerator[str | bytes]:
        url = f"{self._url}/feed/{socket}"
        if not self._reconnect:
            async with connect(url, max_size=None, compression=None) as connection:
                async for data in connection:
                    yield data
            return
        async for connection in connect(url, max_size=None, compression=None):
            try:
                async for data in connection:
                    yield data
            except ConnectionClosed:
                continue


__all__ = ["FeedClient"]
