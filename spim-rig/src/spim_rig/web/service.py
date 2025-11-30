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
from spim_rig.config import SpimRigConfig

router = APIRouter()
log = logging.getLogger(__name__)


class RigStatus(BaseModel):
    """Runtime state of the rig.

    For static configuration (profiles, channels, stage, daq, etc.),
    use the GET /config endpoint.
    """

    active_profile_id: str | None
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

        # Subscribe to device property streams in background
        asyncio.create_task(self._subscribe_to_device_streams())

    @property
    def status(self) -> RigStatus:
        return RigStatus(
            active_profile_id=self.rig.active_profile_id,
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
                case "rig/request_status":
                    await self._broadcast_rig_status()
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
                case "device/set_property":
                    await self._handle_device_set_property(payload)
                case "device/execute_command":
                    await self._handle_device_execute_command(payload)
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

    async def _handle_device_set_property(self, payload: dict[str, Any]):
        """Handle device property update from WebSocket."""
        device_id = payload.get("device")
        properties = payload.get("properties", {})

        if not device_id:
            raise ValueError("Missing 'device' in payload")
        if not properties:
            raise ValueError("Missing 'properties' in payload")

        await self.set_device_properties(device_id, properties)

    async def _handle_device_execute_command(self, payload: dict[str, Any]):
        """Handle device command execution from WebSocket."""
        device_id = payload.get("device")
        command = payload.get("command")
        args = payload.get("args", [])
        kwargs = payload.get("kwargs", {})

        if not device_id:
            raise ValueError("Missing 'device' in payload")
        if not command:
            raise ValueError("Missing 'command' in payload")

        await self.execute_device_command(device_id, command, args, kwargs)

    async def set_device_properties(self, device_id: str, properties: dict[str, Any]):
        """Set device properties and broadcast to all clients.

        Args:
            device_id: The device identifier
            properties: Dictionary of property_name -> value pairs

        Returns:
            PropsResponse with device_id, res, and err
        """
        client = self.rig.devices.get(device_id)
        if not client:
            raise ValueError(f"Device '{device_id}' not found")

        # Set properties
        result = await client.set_props(**properties)

        if result.err:
            log.warning(f"Errors setting properties on {device_id}: {result.err}")

        # Broadcast to all clients (including sender)
        # Topic: device/<device_id>/properties
        # Payload: PropsResponse (without device_id, as it's in the topic)
        await self._broadcast(f"device/{device_id}/properties", result.model_dump())

        return {"device": device_id, **result.model_dump()}

    async def execute_device_command(self, device_id: str, command: str, args: list[Any], kwargs: dict[str, Any]):
        """Execute a command on a device and broadcast result to all clients.

        Args:
            device_id: The device identifier
            command: The command name to execute
            args: Positional arguments for the command
            kwargs: Keyword arguments for the command

        Returns:
            CommandResponse with device_id, command, and result/error
        """
        client = self.rig.devices.get(device_id)
        if not client:
            raise ValueError(f"Device '{device_id}' not found")

        # Execute command
        response = await client.send_command(command, *args, **kwargs)

        result_payload = {
            "device": device_id,
            "command": command,
            "success": response.is_ok,
            "result": response.res if response.is_ok else None,
            "error": response.res.msg if not response.is_ok else None,
        }

        if not response.is_ok:
            log.warning(f"Error executing {command} on {device_id}: {response.res.msg}")

        # Broadcast to all clients (including sender)
        # Topic: device/<device_id>/command_result
        await self._broadcast(f"device/{device_id}/command_result", result_payload)

        return result_payload

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

    async def _subscribe_to_device_streams(self):
        """Subscribe to device streams and forward them to WebSocket clients."""
        for device_id, client in self.rig.devices.items():

            def make_forwarder(dev_id: str):
                def forwarder(topic: str, payload_bytes: bytes):
                    try:
                        # Parse the payload
                        payload = json.loads(payload_bytes.decode("utf-8"))

                        # Extract topic suffix after device_id/
                        # e.g., "camera1/properties" -> "properties"
                        topic_suffix = topic.split("/", 1)[1] if "/" in topic else topic

                        # Broadcast as device/{device_id}/{topic_suffix}
                        asyncio.create_task(self._broadcast(f"device/{dev_id}/{topic_suffix}", payload))
                    except Exception as e:
                        log.error(f"Error forwarding {topic} for {dev_id}: {e}")

                return forwarder

            # Subscribe with empty string to forward all topics
            await client.subscribe("", make_forwarder(device_id))
            log.debug(f"Forwarding all topics for device: {device_id}")

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

    shutdown = asyncio.Event()

    async def sender():
        """Send messages from queue to client."""
        try:
            while not shutdown.is_set():
                try:
                    msg_type, data = await asyncio.wait_for(message_queue.get(), timeout=0.1)
                    if msg_type == "json":
                        await websocket.send_json(data)
                    elif msg_type == "bytes":
                        await websocket.send_bytes(data)
                except TimeoutError:
                    continue
        except Exception as e:
            log.debug("Sender task ending for client %s: %s", client_id, e)
        finally:
            shutdown.set()

    async def receiver():
        """Receive messages from client."""
        try:
            while not shutdown.is_set():
                data = await websocket.receive_text()
                message = json.loads(data)
                await service.handle_client_message(client_id, message)
        except WebSocketDisconnect:
            log.debug("Client %s disconnected", client_id)
        except json.JSONDecodeError as e:
            log.error("Invalid JSON from client %s: %s", client_id, e)
        except Exception as e:
            log.debug("Receiver task ending for client %s: %s", client_id, e)
        finally:
            shutdown.set()

    try:
        await asyncio.gather(sender(), receiver())
    except asyncio.CancelledError:
        log.debug("WebSocket tasks cancelled for client %s", client_id)
    finally:
        shutdown.set()
        service.remove_client(client_id)
        # Auto-stop preview if this was a client that requested it
        if service._preview_start_count > 0:
            await service._handle_preview_stop()


@router.get("/config", tags=["config"])
async def get_config(rig: SpimRig = Depends(get_rig)) -> SpimRigConfig:
    return rig.config


class SetProfileRequest(BaseModel):
    """Request model for setting active profile."""

    profile_id: str


@router.post("/profiles/active", tags=["profiles"])
async def set_active_profile(request: SetProfileRequest, service: RigService = Depends(get_rig_service)) -> dict:
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


@router.get("/devices", tags=["devices"])
async def list_devices(rig: SpimRig = Depends(get_rig)) -> dict:
    """Get list of all devices with their interfaces.

    Returns detailed information about all provisioned devices including their
    properties, commands, and metadata. This is useful for introspection and
    building dynamic UIs.

    Returns:
        Dictionary mapping device_id to device info including interface details.
    """
    devices_info = {}

    for device_id, client in rig.devices.items():
        try:
            interface = await client.get_interface()
            devices_info[device_id] = {
                "id": device_id,
                "connected": client.is_connected,
                "interface": interface.model_dump(),
            }
        except Exception as e:
            log.warning(f"Failed to get interface for device {device_id}: {e}")
            devices_info[device_id] = {
                "id": device_id,
                "connected": client.is_connected,
                "error": str(e),
            }

    return {
        "devices": devices_info,
        "count": len(devices_info),
    }


@router.get("/devices/{device_id}/properties", tags=["devices"])
async def get_device_properties(
    device_id: str,
    rig: SpimRig = Depends(get_rig),
    props: list[str] | None = None,
) -> dict:
    """Get property values from a device.

    Args:
        device_id: The device identifier
        props: Optional list of property names to fetch. If None, fetches all properties.

    Returns:
        Dictionary with device_id and PropertyModel values in res/err format

    Example:
        GET /devices/laser_488/properties
        GET /devices/laser_488/properties?props=power&props=enabled
    """
    try:
        client = rig.devices.get(device_id)
        if not client:
            raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

        # Get properties
        if props:
            result = await client.get_props(*props)
        else:
            # Get all properties from interface
            interface = await client.get_interface()
            prop_names = list(interface.properties.keys())
            result = await client.get_props(*prop_names)

        return {
            "device": device_id,
            **result.model_dump(),
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get properties from device {device_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/devices/{device_id}/properties", tags=["devices"])
async def set_device_properties(
    device_id: str,
    properties: dict[str, Any],
    service: RigService = Depends(get_rig_service),
) -> dict:
    """Set one or more properties on a device.

    Updates are broadcast to all WebSocket clients in real-time.

    Args:
        device_id: The device identifier
        properties: Dictionary of property_name -> value pairs

    Returns:
        Updated property values and any errors
    """
    try:
        return await service.set_device_properties(device_id, properties)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to set properties on device {device_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class ExecuteCommandRequest(BaseModel):
    """Request model for executing a device command."""

    args: list[Any] = []
    kwargs: dict[str, Any] = {}


@router.post("/devices/{device_id}/commands/{command_name}", tags=["devices"])
async def execute_device_command(
    device_id: str,
    command_name: str,
    request: ExecuteCommandRequest = ExecuteCommandRequest(),
    service: RigService = Depends(get_rig_service),
) -> dict:
    """Execute a command on a device.

    Command results are broadcast to all WebSocket clients in real-time.

    Args:
        device_id: The device identifier
        command_name: The name of the command to execute
        request: Optional command arguments (args and kwargs)

    Returns:
        Command execution result with success status and result/error

    Example:
        POST /devices/laser_488/commands/enable
        POST /devices/stage/commands/move_to {"kwargs": {"x": 100, "y": 200}}
    """
    try:
        return await service.execute_device_command(device_id, command_name, request.args, request.kwargs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to execute command {command_name} on device {device_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
