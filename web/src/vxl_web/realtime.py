"""StationFeed-backed state and preview WebSocket delivery."""

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from rigup.wire import pack, unpack
from vxl_records import LogEntry

from vxl.preview import LatestFrameQueue, PreviewEmission, PreviewKey, PreviewViewport
from vxl.station import Station, StationFeedConnection, StationFeedLaggedError, StationFeedView, StationState
from vxlib import SchemaModel

if TYPE_CHECKING:
    from vxlib import Teardown

log = logging.getLogger(__name__)


class PreviewViewportUpdate(SchemaModel):
    """Latest requested preview viewport for one expected instrument session."""

    action: Literal["preview.viewport.update"]
    session_id: UUID
    viewport: PreviewViewport


class _PreviewClient:
    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._queue = LatestFrameQueue()

    def publish(self, key: PreviewKey, packet: bytes) -> None:
        self._queue.put(key, packet)

    def clear(self) -> None:
        self._queue.clear()

    async def serve(self) -> None:
        sender = asyncio.create_task(self._send(), name="station-preview-send")
        receiver = asyncio.create_task(self._receive(), name="station-preview-receive")
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
            _key, packet = await self._queue.get()
            await self._websocket.send_bytes(packet)

    async def _receive(self) -> None:
        while True:
            if (await self._websocket.receive())["type"] == "websocket.disconnect":
                return


class _LogClient:
    """Bound one live log viewer without ever slowing journal commits."""

    def __init__(self, websocket: WebSocket, *, queue_size: int = 200) -> None:
        self._websocket = websocket
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=queue_size)

    def publish(self, entry: LogEntry) -> None:
        packet = cast("bytes", pack(entry))
        if self._queue.full():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
        self._queue.put_nowait(packet)

    async def serve(self) -> None:
        sender = asyncio.create_task(self._send(), name="station-log-send")
        receiver = asyncio.create_task(self._receive(), name="station-log-receive")
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
            await self._websocket.send_bytes(await self._queue.get())

    async def _receive(self) -> None:
        while True:
            if (await self._websocket.receive())["type"] == "websocket.disconnect":
                return


class Realtime:
    """Serve complete StationFeed views and latest-only preview packets."""

    def __init__(self, station: Station) -> None:
        self._station = station
        self._state_clients: set[WebSocket] = set()
        self._preview_clients: set[_PreviewClient] = set()
        self._log_clients: set[_LogClient] = set()
        self._preview_identity = self._get_preview_identity(station.state.value)
        self._teardowns: list[Teardown] = [
            station.feed.frames.subscribe(self._publish_preview),
            station.state.subscribe(self._on_station_state),
            station.records.logs.subscribe(self._publish_log),
        ]

    async def serve_state(self, websocket: WebSocket) -> None:
        """Send one atomic initial StationFeed view followed by every later complete view."""
        await websocket.accept()
        self._state_clients.add(websocket)
        try:
            async with self._station.feed.connect() as connection:
                sender = asyncio.create_task(self._send_state(websocket, connection), name="station-state-send")
                receiver = asyncio.create_task(self._receive(websocket), name="station-state-receive")
                done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        except StationFeedLaggedError:
            log.warning("Disconnecting a lagged station-state WebSocket")
        except (RuntimeError, WebSocketDisconnect):
            pass
        finally:
            self._state_clients.discard(websocket)
            with suppress(Exception):
                await websocket.close()

    async def serve_preview(self, websocket: WebSocket) -> None:
        """Send latest-only opaque Station preview packets until the client disconnects."""
        await websocket.accept()
        client = _PreviewClient(websocket)
        self._preview_clients.add(client)
        try:
            await client.serve()
        except (RuntimeError, WebSocketDisconnect):
            pass
        finally:
            self._preview_clients.discard(client)
            await client.close()

    async def serve_logs(self, websocket: WebSocket) -> None:
        """Send newly committed log entries without coupling clients to journal writes."""
        await websocket.accept()
        client = _LogClient(websocket)
        self._log_clients.add(client)
        try:
            await client.serve()
        except (RuntimeError, WebSocketDisconnect):
            pass
        finally:
            self._log_clients.discard(client)
            await client.close()

    async def close(self) -> None:
        """Detach Station subscriptions and close every connected WebSocket."""
        for teardown in self._teardowns:
            teardown()
        self._teardowns = []
        state_clients = tuple(self._state_clients)
        self._state_clients.clear()
        preview_clients = tuple(self._preview_clients)
        self._preview_clients.clear()
        log_clients = tuple(self._log_clients)
        self._log_clients.clear()
        await asyncio.gather(
            *(self._close_websocket(websocket) for websocket in state_clients),
            *(client.close() for client in preview_clients),
            *(client.close() for client in log_clients),
        )

    async def _send_state(self, websocket: WebSocket, connection: StationFeedConnection) -> None:
        await self._send_view(websocket, connection.initial)
        async for view in connection:
            await self._send_view(websocket, view)

    @staticmethod
    async def _send_view(websocket: WebSocket, view: StationFeedView) -> None:
        await websocket.send_bytes(cast("bytes", pack(view)))

    async def _receive(self, websocket: WebSocket) -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            payload = message.get("bytes")
            if payload is None:
                log.warning("Ignoring a non-binary station control message")
                continue
            try:
                update = PreviewViewportUpdate.model_validate(unpack(payload))
            except Exception as error:
                log.warning("Ignoring an invalid preview viewport message: %s", error)
                continue
            try:
                async with self._station.instrument(update.session_id) as instrument:
                    instrument.update_viewport(update.viewport)
            except RuntimeError as error:
                log.debug("Ignoring a preview viewport update for an unavailable session: %s", error)

    @staticmethod
    async def _close_websocket(websocket: WebSocket) -> None:
        with suppress(Exception):
            await websocket.close()

    def _publish_preview(self, emission: PreviewEmission) -> None:
        channel_id, layer, packet = emission
        key = (channel_id, layer)
        for client in tuple(self._preview_clients):
            client.publish(key, packet)

    def _publish_log(self, entry: LogEntry) -> None:
        for client in tuple(self._log_clients):
            client.publish(entry)

    def _on_station_state(self, state: StationState) -> None:
        identity = self._get_preview_identity(state)
        if identity == self._preview_identity:
            return
        self._preview_identity = identity
        for client in tuple(self._preview_clients):
            client.clear()

    @staticmethod
    def _get_preview_identity(state: StationState) -> tuple[object, int] | None:
        if state.session is None:
            return None
        return state.session.info.id, state.session.info.preview_revision


__all__ = ["PreviewViewportUpdate", "Realtime"]
