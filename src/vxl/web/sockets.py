"""The 2 WebSockets that give the feed of 1 service to its readers, and the listener that serves them."""

import asyncio
import contextlib
import logging
import socket
from collections.abc import Awaitable, Callable, Generator
from http import HTTPStatus
from types import TracebackType
from typing import Any, Self

import uvicorn
from starlette.responses import Response
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from vxl.web.feed import FeedConnection, FeedRelay, FrameMessage, StateMessage


class FeedSockets:
    """The state socket and the frame socket of a relay, as routes of a Starlette or FastAPI app:
    ``<prefix>/feed/state`` sends each state message as JSON text, and ``<prefix>/feed/frames`` sends each frame
    message as 1 VXFP packet. A message is written 1 time for the readers that get it together. A reader sends
    nothing. While the relay is closed, both refuse a reader with ``503``, which a reader takes as "try again"."""

    def __init__(self, relay: FeedRelay) -> None:
        self._relay = relay
        self._text: tuple[StateMessage, str] | None = None
        self._packet: tuple[FrameMessage, bytes] | None = None

    def routes(self, prefix: str = "") -> list[WebSocketRoute]:
        """The 2 socket routes, under ``prefix``."""
        return [
            WebSocketRoute(f"{prefix}/feed/state", self._state),
            WebSocketRoute(f"{prefix}/feed/frames", self._frames),
        ]

    async def _state(self, socket: WebSocket) -> None:
        if self._relay.closed:
            await socket.send_denial_response(Response(status_code=HTTPStatus.SERVICE_UNAVAILABLE))
            return
        with self._relay.connect() as connection:
            await self._serve(socket, connection, lambda message: socket.send_text(self._as_text(message)))

    async def _frames(self, socket: WebSocket) -> None:
        if self._relay.closed:
            await socket.send_denial_response(Response(status_code=HTTPStatus.SERVICE_UNAVAILABLE))
            return
        with self._relay.connect_frames() as connection:
            await self._serve(socket, connection, lambda message: socket.send_bytes(self._as_packet(message)))

    def _as_text(self, message: StateMessage) -> str:
        if self._text is None or self._text[0] is not message:
            self._text = (message, message.model_dump_json(warnings=False))
        return self._text[1]

    def _as_packet(self, message: FrameMessage) -> bytes:
        if self._packet is None or self._packet[0] is not message:
            self._packet = (message, message.pack())
        return self._packet[1]

    @staticmethod
    async def _serve[M: (StateMessage, FrameMessage)](
        socket: WebSocket, connection: FeedConnection[M], send: Callable[[M], Awaitable[None]]
    ) -> None:
        """Send each message of ``connection`` until the reader leaves or the feed closes."""
        await socket.accept()

        async def forward() -> None:
            async for message in connection:
                await send(message)

        async def until_gone() -> None:
            while (await socket.receive())["type"] != "websocket.disconnect":
                pass

        tasks = {asyncio.create_task(forward()), asyncio.create_task(until_gone())}
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):  # the reader already left
            await socket.close()


class _EmbeddedServer(uvicorn.Server):
    """A uvicorn server that leaves signals to the program around it."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield


class Listener:
    """Serves an ASGI app on 1 address inside the running event loop, from ``async with`` until its end. ``port`` 0
    takes a free port; :attr:`port` gives the port in use. Entering raises :class:`OSError` when the address is
    taken."""

    def __init__(self, app: Any, *, host: str = "127.0.0.1", port: int = 0) -> None:
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_config=None,
            log_level="warning",
            access_log=False,  # a line for each request would fill the station's log
            lifespan="off",
            ws_max_size=2**31 - 1,
            ws_per_message_deflate=False,  # frames are compressed already
            timeout_graceful_shutdown=2,
        )
        self._server = _EmbeddedServer(config)
        logging.getLogger("uvicorn.error").addFilter(self._not_a_refusal)  # the same function: added 1 time
        self._task: asyncio.Task[None] | None = None
        self.host = host
        self.port = port

    @staticmethod
    def _not_a_refusal(record: logging.LogRecord) -> bool:
        """Whether a log line of uvicorn is not its false error after a refused socket: uvicorn 0.52 logs that error
        when an app answers a socket with an HTTP status (``send_denial_response``), and still sends the status."""
        return record.getMessage() != "ASGI callable returned without completing handshake."

    async def __aenter__(self) -> Self:
        listening = socket.create_server((self.host, self.port), backlog=2048)  # here, so that a taken port raises
        self.port = listening.getsockname()[1]
        self._task = asyncio.create_task(self._server.serve(sockets=[listening]))
        while not self._server.started:
            if self._task.done():
                await self._task  # raises why it did not start
                raise RuntimeError(f"cannot listen on {self.host}:{self.port}")
            await asyncio.sleep(0.005)
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        self._server.should_exit = True
        if self._task is not None:
            await self._task


__all__ = ["FeedSockets", "Listener"]
