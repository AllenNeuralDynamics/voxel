"""WebSocket endpoint for broadcasting rig control events."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect

from spim_rig import SpimRig

router = APIRouter()
log = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    """Return an ISO 8601 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


class ControlService:
    """Broadcasts rig control state (active profile, etc.) to connected clients."""

    def __init__(self, rig: SpimRig):
        self.rig = rig
        self.clients: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    async def add_client(self, client_id: str, queue: asyncio.Queue[dict[str, Any]]):
        """Register a new client and push the current snapshot."""
        self.clients[client_id] = queue
        log.info("Control client %s connected. Total: %d", client_id, len(self.clients))
        await queue.put({"type": "control:ready", "timestamp": _utc_timestamp()})
        await queue.put(self._profile_event())

    def remove_client(self, client_id: str):
        """Remove a client subscription."""
        self.clients.pop(client_id, None)
        log.info("Control client %s disconnected. Total: %d", client_id, len(self.clients))

    async def emit_profile_change(self):
        """Broadcast that the active profile changed."""
        await self._broadcast(self._profile_event())

    def _profile_event(self) -> dict[str, Any]:
        """Build the payload describing current active profile."""
        return {
            "type": "profiles:active_changed",
            "active_profile_id": self.rig.active_profile_id,
            "channels": list(self.rig.active_channels.keys()),
            "timestamp": _utc_timestamp(),
        }

    async def _broadcast(self, message: dict[str, Any]):
        """Send a JSON message to all clients."""
        to_drop: list[str] = []
        for client_id, queue in self.clients.items():
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("Control client %s queue full; dropping event.", client_id)
                to_drop.append(client_id)
        for client_id in to_drop:
            self.remove_client(client_id)


def get_control_service(websocket: WebSocket) -> ControlService:
    """Dependency helper for WebSocket routes."""
    return websocket.app.state.control_service


def get_control_service_from_request(request: Request) -> ControlService:
    """Dependency helper for HTTP routes."""
    return request.app.state.control_service


@router.websocket("/ws/control")
async def control_websocket(websocket: WebSocket, service: ControlService = Depends(get_control_service)):
    """WebSocket endpoint that streams control events to clients."""
    await websocket.accept()
    client_id = str(uuid.uuid4())
    event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)
    await service.add_client(client_id, event_queue)

    async def sender():
        while True:
            payload = await event_queue.get()
            await websocket.send_json(payload)

    async def receiver():
        # Keep reading client messages (if any) to detect disconnects.
        while True:
            await websocket.receive_text()

    sender_task: asyncio.Task | None = None
    receiver_task: asyncio.Task | None = None
    try:
        sender_task = asyncio.create_task(sender())
        receiver_task = asyncio.create_task(receiver())
        done, pending = await asyncio.wait(
            [sender_task, receiver_task],
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in pending:
            task.cancel()

        for task in done:
            task.result()
    except WebSocketDisconnect:
        log.info("Control WebSocket %s disconnected", client_id)
    finally:
        for task in (sender_task, receiver_task):
            if task and not task.done():
                task.cancel()
        service.remove_client(client_id)
