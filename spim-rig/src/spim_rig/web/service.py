"""Unified WebSocket service for rig control and preview streaming.

This service replaces the separate PreviewService and ControlService with a
unified topic-based routing system using slash notation (e.g., 'rig/status',
'preview/frame', 'profile/changed').
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from spim_rig import SpimRig
from spim_rig.camera.preview import PreviewCrop, PreviewLevels
from spim_rig.rig import ChannelConfig, ProfileConfig

router = APIRouter()
log = logging.getLogger(__name__)


class RigStatus(BaseModel):
    active_profile_id: str | None
    profiles: dict[str, ProfileConfig]
    channels: dict[str, ChannelConfig]
    previewing: bool
    timestamp: str


def _utc_timestamp() -> str:
    """Return an ISO 8601 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


class RigService:
    """Unified service for all rig WebSocket communication.

    Uses slash-notation topics for routing:
    - rig/status - Full rig state snapshot
    - preview/frame - Preview frame data
    - preview/crop - Preview crop/zoom changed
    - preview/levels - Preview levels changed
    """

    def __init__(self, rig: SpimRig):
        self.rig = rig
        self.clients: dict[str, asyncio.Queue[tuple[str, Any]]] = {}
        self._preview_start_count = 0
        self._preview_lock = asyncio.Lock()

    @property
    def status(self) -> RigStatus:
        return RigStatus(
            active_profile_id=self.rig.active_profile_id,
            profiles=self.rig.config.profiles,
            channels=self.rig.config.channels,
            previewing=self.rig.preview.is_active,
            timestamp=_utc_timestamp(),
        )

    async def add_client(self, client_id: str, queue: asyncio.Queue[tuple[str, Any]]):
        """Register a new client and send initial state snapshot."""
        self.clients[client_id] = queue
        log.info("Client %s connected. Total: %d", client_id, len(self.clients))
        await self._send_to_client(queue, "rig/status", self.status.model_dump())

    def remove_client(self, client_id: str):
        """Remove a client from the distribution list."""
        self.clients.pop(client_id, None)
        log.info("Client %s disconnected. Total: %d", client_id, len(self.clients))

    async def handle_client_message(self, client_id: str, message: dict[str, Any]):
        """Handle incoming message from a client."""
        topic = message.get("topic")
        payload = message.get("payload", {})

        try:
            match topic:
                case "profile/update":
                    await self.handle_profile_change(payload)
                case "preview/start":
                    await self._handle_preview_start()
                case "preview/stop":
                    await self._handle_preview_stop()
                case "preview/crop":
                    await self._handle_preview_crop(payload)
                case "preview/levels":
                    await self._handle_preview_levels(payload)
                case _:
                    log.warning("Unknown message topic from client %s: %s", client_id, topic)
        except Exception as e:
            log.error("Error handling message from client %s: %s", client_id, e)
            await self._send_to_client(self.clients.get(client_id), "rig/error", {"error": str(e), "topic": topic})

    async def handle_profile_change(self, payload: dict[str, Any] | str):
        """Handle profile change from WebSocket message."""
        # Support both dict payload and string payload
        profile_id = payload.get("profile_id") if isinstance(payload, dict) else payload
        if not profile_id:
            raise ValueError("Missing profile_id")
        await self.rig.set_active_profile(profile_id)
        await self._broadcast_rig_status()

    async def _handle_preview_start(self):
        """Start preview streaming."""
        async with self._preview_lock:
            if self._preview_start_count == 0:
                log.info("First client requested preview. Starting rig preview.")
                await self.rig.start_preview(frame_callback=self._distribute_frames)
            self._preview_start_count += 1
            log.debug("Preview start count: %d", self._preview_start_count)

        await self._broadcast_preview_status()

    async def _handle_preview_stop(self):
        """Stop preview streaming."""
        async with self._preview_lock:
            if self._preview_start_count > 0:
                self._preview_start_count -= 1
            log.debug("Preview start count: %d", self._preview_start_count)

            if self._preview_start_count == 0 and self.rig.preview.is_active:
                log.info("Last client stopped preview. Stopping rig preview.")
                await self.rig.stop_preview()

        await self._broadcast_preview_status()

    async def _handle_preview_crop(self, payload: dict[str, Any]):
        """Handle preview crop update."""
        try:
            crop = PreviewCrop(x=payload.get("x", 0), y=payload.get("y", 0), k=payload.get("k", 0))

            tasks = []
            for channel in self.rig.active_channels.values():
                if camera := self.rig.cameras.get(channel.detection):
                    tasks.append(camera.update_preview_crop(crop))
            await asyncio.gather(*tasks)

            await self._broadcast("preview/crop", {"x": crop.x, "y": crop.y, "k": crop.k})
        except Exception as e:
            log.error("Error updating preview crop: %s", e)
            raise

    async def _handle_preview_levels(self, payload: dict[str, Any]):
        """Handle preview levels update for a specific channel."""
        try:
            channel_id = payload.get("channel")
            if not channel_id:
                raise ValueError("Missing 'channel' in levels payload")

            levels = PreviewLevels(min=payload.get("min", 0), max=payload.get("max", 255))

            if channel := self.rig.active_channels.get(channel_id):
                if camera := self.rig.cameras.get(channel.detection):
                    await camera.update_preview_levels(levels)
                    await self._broadcast(
                        "preview/levels", {"channel": channel_id, "min": levels.min, "max": levels.max}
                    )
        except Exception as e:
            log.error("Error updating preview levels: %s", e)
            raise

    async def _distribute_frames(self, channel: str, packed_frame: bytes) -> None:
        """Callback that distributes preview frames to all clients.

        Frames use hybrid format: JSON envelope + newline + msgpack data.
        """
        envelope = json.dumps({"topic": "preview/frame", "channel": channel}).encode("utf-8")
        message = envelope + b"\n" + packed_frame

        for queue in self.clients.values():
            try:
                queue.put_nowait(("bytes", message))
            except asyncio.QueueFull:
                pass  # Don't warn on dropped frames, too noisy

    async def _broadcast_rig_status(self):
        await self._broadcast("rig/status", self.status.model_dump())

    async def _broadcast_preview_status(self):
        """Broadcast the current previewing status."""
        await self._broadcast(
            "preview/status",
            {"previewing": self.rig.preview.is_active, "timestamp": _utc_timestamp()},
        )

    async def _broadcast(self, topic: str, payload: dict[str, Any]):
        """Broadcast a JSON message to all connected clients."""
        message = {"topic": topic, "payload": payload}
        for client_id, queue in self.clients.items():
            try:
                await queue.put(("json", message))
            except asyncio.QueueFull:
                log.warning("Client %s queue full, dropping message: %s", client_id, topic)

    async def _send_to_client(self, queue: asyncio.Queue | None, topic: str, payload: dict[str, Any]):
        """Send a JSON message to a specific client."""
        if queue is None:
            return

        message = {"topic": topic, "payload": payload}
        try:
            await queue.put(("json", message))
        except asyncio.QueueFull:
            log.warning("Client queue full, dropping message: %s", topic)


def get_rig(request: Request) -> SpimRig:
    """Dependency to get the SpimRig instance from app state."""
    return request.app.state.rig


def get_rig_service_websocket(websocket: WebSocket) -> RigService:
    """Dependency helper for WebSocket routes."""
    return websocket.app.state.rig_service


def get_rig_service(request: Request) -> RigService:
    """Dependency helper for HTTP routes."""
    return request.app.state.rig_service


@router.websocket("/ws/rig")
async def rig_websocket(websocket: WebSocket, service: RigService = Depends(get_rig_service_websocket)):
    """Unified WebSocket endpoint for all rig communication."""
    await websocket.accept()
    client_id = str(uuid.uuid4())
    message_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=100)

    await service.add_client(client_id, message_queue)

    async def sender():
        """Send messages from queue to client."""
        while True:
            msg_type, data = await message_queue.get()
            if msg_type == "json":
                await websocket.send_json(data)
            elif msg_type == "bytes":
                await websocket.send_bytes(data)

    async def receiver():
        """Receive messages from client."""
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await service.handle_client_message(client_id, message)
            except json.JSONDecodeError as e:
                log.error("Invalid JSON from client %s: %s", client_id, e)
            except Exception as e:
                log.error("Error processing client message: %s", e)

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
        log.info("Client %s disconnected", client_id)
    except Exception as e:
        log.error("WebSocket error for client %s: %s", client_id, e)
    finally:
        for task in (sender_task, receiver_task):
            if task and not task.done():
                task.cancel()
        service.remove_client(client_id)


class SetProfileRequest(BaseModel):
    """Request model for setting active profile."""

    profile_id: str


@router.post("/profiles/active", tags=["profiles"])
async def set_active_profile(
    request: SetProfileRequest,
    service: RigService = Depends(get_rig_service),
) -> dict:
    """Set the active profile via REST API.

    This will configure devices (filter wheels, etc.) for the new profile.
    If preview is running, it will seamlessly transition to the new profile's cameras.
    All WebSocket clients will be notified with updated rig status.

    Args:
        request: Request containing the profile_id to activate.

    Returns:
        Success message with the new active profile ID and channels.

    Raises:
        HTTPException: If profile_id does not exist or activation fails.
    """
    try:
        await service.handle_profile_change(request.profile_id)
        log.info(f"Active profile set to '{request.profile_id}' via REST")

        return service.status.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"Failed to set active profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set active profile: {str(e)}")


@router.get("/profiles", tags=["profiles"])
async def list_profiles(rig: SpimRig = Depends(get_rig)) -> dict:
    """Get list of all available profiles.

    Note: This information is also available via WebSocket in the rig/status message.
    This REST endpoint is provided for convenience and non-WebSocket clients.

    Returns:
        Dictionary with profiles and active_profile_id.
    """
    return {
        "profiles": {
            profile_id: {
                "id": profile_id,
                "label": profile_config.label,
                "desc": profile_config.desc,
                "channels": profile_config.channels,
            }
            for profile_id, profile_config in rig.config.profiles.items()
        },
        "active_profile_id": rig.active_profile_id,
    }
