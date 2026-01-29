"""Rig-level service for device control and preview streaming.

This service handles rig operations: profiles, preview, devices, DAQ.
It receives a broadcast callback from SessionService for client communication.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from pyrig.device import PropsResponse

from voxel import VoxelRig
from voxel.camera.preview import PreviewCrop, PreviewLevels
from voxel.config import VoxelRigConfig
from vxlib import fire_and_forget

router = APIRouter(tags=["rig"])
log = logging.getLogger(__name__)


class BroadcastCallback(Protocol):
    """Protocol for broadcast callback with optional status update."""

    def __call__(self, data: dict[str, Any] | bytes, with_status: bool = False) -> None: ...


def _utc_timestamp() -> str:
    """Return an ISO 8601 timestamp in UTC."""
    return datetime.now(UTC).isoformat()


class RigService:
    """Service for rig-level operations: profiles, preview, devices, DAQ.

    Receives a broadcast callback from SessionService for client communication.
    """

    def __init__(self, rig: VoxelRig, broadcast: BroadcastCallback):
        self.rig = rig
        self._broadcast = broadcast
        self._preview_lock = asyncio.Lock()

        # Subscribe to device property streams in background
        fire_and_forget(self._subscribe_to_device_streams(), log=log)

    async def handle_message(self, topic: str, payload: dict[str, Any]) -> bool:
        """Handle rig-related messages. Returns True if handled."""
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
                case "device/set_property":
                    await self._handle_device_set_property(payload)
                case "device/execute_command":
                    await self._handle_device_execute_command(payload)
                case "daq/request_waveforms":
                    await self._broadcast_waveforms()
                case _:
                    return False
            return True
        except Exception as e:
            log.exception("Error handling rig message %s", topic)
            self._broadcast({"topic": "error", "payload": {"error": str(e), "topic": topic}})
            return True

    # ==================== Profile ====================

    async def handle_profile_change(self, payload: dict[str, Any] | str):
        """Handle profile change from WebSocket message."""
        profile_id = payload.get("profile_id") if isinstance(payload, dict) else payload
        if not profile_id:
            raise ValueError("Missing profile_id")
        await self.rig.set_active_profile(profile_id)
        await self._broadcast_waveforms()
        self._broadcast({"topic": "profile/changed", "payload": {"profile_id": profile_id}}, with_status=True)

    # ==================== Preview ====================

    async def _handle_preview_start(self):
        """Start preview streaming."""
        async with self._preview_lock:
            if not self.is_previewing:
                log.info("Starting rig preview")
                await self.rig.start_preview(frame_callback=self._distribute_frames)

        await self._broadcast_preview_status()

    async def _handle_preview_stop(self):
        """Stop preview streaming."""
        async with self._preview_lock:
            if self.is_previewing:
                log.info("Stopping rig preview")
                await self.rig.stop_preview()

        await self._broadcast_preview_status()

    async def stop_preview(self):
        """Stop preview (used during last client disconnect)."""
        async with self._preview_lock:
            if self.is_previewing:
                log.info("Last client disconnected. Stopping rig preview.")
                await self.rig.stop_preview()
        await self._broadcast_preview_status()

    async def _handle_preview_crop(self, payload: dict[str, Any]):
        """Handle preview crop update."""
        crop = PreviewCrop(x=payload.get("x", 0), y=payload.get("y", 0), k=payload.get("k", 0))
        await self.rig.update_preview_crop(crop)
        self._broadcast({"topic": "preview/crop", "payload": {"x": crop.x, "y": crop.y, "k": crop.k}})

    async def _handle_preview_levels(self, payload: dict[str, Any]):
        """Handle preview levels update for a specific channel."""
        channel_id = payload.get("channel")
        if not channel_id:
            raise ValueError("Missing 'channel' in levels payload")

        levels = PreviewLevels(min=payload.get("min", 0), max=payload.get("max", 255))
        await self.rig.update_preview_levels({channel_id: levels})
        self._broadcast(
            {
                "topic": "preview/levels",
                "payload": {"channel": channel_id, "min": levels.min, "max": levels.max},
            },
        )

    async def _distribute_frames(self, channel: str, packed_frame: bytes) -> None:
        """Callback that distributes preview frames to all clients.

        Frames use hybrid format: JSON envelope + newline + msgpack data.
        """
        envelope = json.dumps({"topic": "preview/frame", "channel": channel}).encode("utf-8")
        self._broadcast(envelope + b"\n" + packed_frame)

    async def _broadcast_preview_status(self):
        """Broadcast the current previewing status (also triggers app status update)."""
        self._broadcast(
            {
                "topic": "preview/status",
                "payload": {"previewing": self.rig.preview.is_active, "timestamp": _utc_timestamp()},
            },
            with_status=True,
        )

    # ==================== Devices ====================

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

    async def set_device_properties(self, device_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Set device properties and broadcast to all clients."""
        client = self.rig.handles.get(device_id)
        if not client:
            raise ValueError(f"Device '{device_id}' not found")

        result = await client.set_props(**properties)

        if result.err:
            log.warning(f"Errors setting properties on {device_id}: {result.err}")

        self._broadcast({"topic": f"device/{device_id}/properties", "payload": result.model_dump()})

        return {"device": device_id, **result.model_dump()}

    async def execute_device_command(
        self,
        device_id: str,
        command: str,
        args: list[Any],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a command on a device and broadcast result to all clients."""
        client = self.rig.handles.get(device_id)
        if not client:
            raise ValueError(f"Device '{device_id}' not found")

        response = await client.run_command(command, *args, **kwargs)

        result_payload = {
            "device": device_id,
            "command": command,
            "success": response.is_ok,
            "result": response.res if response.is_ok else None,
            "error": response.res.msg if not response.is_ok else None,
        }

        if not response.is_ok:
            log.warning(f"Error executing {command} on {device_id}: {response.res.msg}")

        self._broadcast({"topic": f"device/{device_id}/command_result", "payload": result_payload})

        return result_payload

    async def _subscribe_to_device_streams(self):
        """Subscribe to device streams and forward them to WebSocket clients."""
        for device_id, handle in self.rig.handles.items():

            def make_forwarder(dev_id: str) -> Callable[[PropsResponse], Awaitable[None]]:
                async def forwarder(props: PropsResponse) -> None:
                    try:
                        payload = props.model_dump()
                        self._broadcast({"topic": f"device/{dev_id}/properties", "payload": payload})
                    except Exception:
                        log.exception(f"Error forwarding properties for {dev_id}")

                return forwarder

            await handle.on_props_changed(make_forwarder(device_id))
            log.debug(f"Subscribed to property updates for device: {device_id}")

    # ==================== DAQ ====================

    async def _broadcast_waveforms(self):
        """Broadcast DAQ waveforms to all clients."""
        if self.rig.sync_task:
            try:
                waveforms = self.rig.sync_task.get_written_waveforms(target_points=1000)
                self._broadcast({"topic": "daq/waveforms", "payload": waveforms})
            except Exception:
                log.exception("Failed to get waveforms")

    @property
    def is_previewing(self) -> bool:
        """Check if preview is active."""
        return self.rig.preview.is_active


# ==================== REST Endpoints ====================


def get_rig(request: Request) -> VoxelRig:
    """Dependency to get the VoxelRig instance from app state."""
    app_service = request.app.state.app_service
    if app_service.session_service is None:
        raise HTTPException(status_code=503, detail="No active session")
    return app_service.session_service.session.rig


def get_rig_service(request: Request) -> RigService:
    """Dependency to get the RigService instance from app state."""
    app_service = request.app.state.app_service
    if app_service.session_service is None:
        raise HTTPException(status_code=503, detail="No active session")
    return app_service.session_service.rig_service


@router.get("/config")
async def get_config(rig: Annotated[VoxelRig, Depends(get_rig)]) -> VoxelRigConfig:
    """Get the full rig configuration."""
    return rig.config


class SetProfileRequest(BaseModel):
    """Request model for setting active profile."""

    profile_id: str


@router.post("/profiles/active")
async def set_active_profile(
    request: SetProfileRequest,
    service: Annotated[RigService, Depends(get_rig_service)],
) -> dict:
    """Set the active profile via REST API.

    This will configure devices (filter wheels, etc.) for the new profile.
    If preview is running, it will seamlessly transition to the new profile's cameras.
    All WebSocket clients will be notified with updated rig status.
    """
    try:
        await service.handle_profile_change(request.profile_id)
        log.info(f"Active profile set to '{request.profile_id}' via REST")
        return {
            "active_profile_id": service.rig.active_profile_id,
            "timestamp": _utc_timestamp(),
        }
    except ValueError as e:
        log.exception(f"ValueError setting active profile to '{request.profile_id}'")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.exception(f"Failed to set active profile to '{request.profile_id}'")
        raise HTTPException(status_code=500, detail=f"Failed to set active profile: {e!s}") from e


@router.get("/devices")
async def list_devices(rig: Annotated[VoxelRig, Depends(get_rig)]) -> dict:
    """Get list of all devices with their interfaces."""
    devices_info = {}

    for device_id, handle in rig.handles.items():
        try:
            interface = await handle.interface()
            devices_info[device_id] = {
                "id": device_id,
                "connected": True,
                "interface": interface.model_dump(),
            }
        except Exception as e:
            log.warning(f"Failed to get interface for device {device_id}: {e}")
            devices_info[device_id] = {
                "id": device_id,
                "connected": False,
                "error": str(e),
            }

    return {
        "devices": devices_info,
        "count": len(devices_info),
    }


@router.get("/devices/{device_id}/properties")
async def get_device_properties(
    device_id: str,
    rig: Annotated[VoxelRig, Depends(get_rig)],
    props: list[str] | None = None,
) -> dict:
    """Get property values from a device."""
    client = rig.handles.get(device_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    try:
        if props:
            result = await client.get_props(*props)
        else:
            interface = await client.interface()
            prop_names = list(interface.properties.keys())
            result = await client.get_props(*prop_names)

        return {
            "device": device_id,
            **result.model_dump(),
        }

    except Exception as e:
        log.exception(f"Failed to get properties from device {device_id}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/devices/{device_id}/properties")
async def set_device_properties_endpoint(
    device_id: str,
    properties: dict[str, Any],
    service: Annotated[RigService, Depends(get_rig_service)],
) -> dict:
    """Set one or more properties on a device."""
    try:
        return await service.set_device_properties(device_id, properties)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"Failed to set properties on device {device_id}")
        raise HTTPException(status_code=500, detail=str(e)) from e


class ExecuteCommandRequest(BaseModel):
    """Request model for executing a device command."""

    args: list[Any] = []
    kwargs: dict[str, Any] = {}


@router.post("/devices/{device_id}/commands/{command_name}")
async def execute_device_command_endpoint(
    device_id: str,
    command_name: str,
    service: Annotated[RigService, Depends(get_rig_service)],
    request: ExecuteCommandRequest | None = None,
) -> dict:
    """Execute a command on a device."""
    if request is None:
        request = ExecuteCommandRequest()
    try:
        return await service.execute_device_command(device_id, command_name, request.args, request.kwargs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"Failed to execute command {command_name} on device {device_id}")
        raise HTTPException(status_code=500, detail=str(e)) from e
