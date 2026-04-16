"""Devices service — direct device-handle access (properties, commands).

Owns ``/devices/*`` REST + ``device/*`` WS. Subscribes to each handle's
``on_props_changed`` to forward property updates to clients.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from rigup import DeviceInterface, PropResults
from vxl import Session

from .ws import BroadcastCallback

log = logging.getLogger(__name__)
router = APIRouter(tags=["devices"])


class DevicesService:
    """REST + WS surface for ``session.microscope.devices``. No controller on the backend."""

    topic_prefixes: tuple[str, ...] = ("device/",)

    def __init__(self, session: Session, broadcast: BroadcastCallback) -> None:
        self.session = session
        self.broadcast = broadcast
        self._unsubs: list[Callable[[], None]] = []

    async def open(self) -> None:
        """Subscribe to every device handle's property-change signal."""
        for device_id, handle in self.session.microscope.devices.items():
            unsub = handle.props_changed.subscribe(self._make_forwarder(device_id))
            self._unsubs.append(unsub)

    async def close(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    # ---- WS ----

    async def handle_message(self, sender_id: str, topic: str, payload: dict[str, Any]) -> None:
        log.debug("devices WS from %s → %s", sender_id, topic)
        match topic:
            case "device/set_property":
                device_id = payload.get("device")
                properties = payload.get("properties", {})
                if not device_id:
                    raise ValueError("Missing 'device' in payload")
                if not properties:
                    raise ValueError("Missing 'properties' in payload")
                await self.set_properties(device_id, properties)
            case "device/execute_command":
                device_id = payload.get("device")
                command = payload.get("command")
                if not device_id:
                    raise ValueError("Missing 'device' in payload")
                if not command:
                    raise ValueError("Missing 'command' in payload")
                await self.execute_command(device_id, command, payload.get("args", []), payload.get("kwargs", {}))

    # ---- Public ops ----

    async def set_properties(self, device_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        handle = self.session.microscope.devices.get(device_id)
        if not handle:
            raise ValueError(f"Device '{device_id}' not found")
        result = await handle.set_props(**properties)
        if not result.is_ok:
            log.warning("Errors setting properties on %s: %s", device_id, result.model_dump())
        self.broadcast({"topic": f"device/{device_id}/properties", "payload": result.model_dump()})
        return {"device": device_id, **result.model_dump()}

    async def execute_command(
        self,
        device_id: str,
        command: str,
        args: list[Any],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        handle = self.session.microscope.devices.get(device_id)
        if not handle:
            raise ValueError(f"Device '{device_id}' not found")
        response = await handle.run_command(command, *args, **kwargs)
        if not response.is_ok:
            log.warning("Error executing %s on %s: %s", command, device_id, response.root.msg)
        payload = {"device": device_id, "command": command, "result": response.model_dump()}
        self.broadcast({"topic": f"device/{device_id}/command_result", "payload": payload})
        return payload

    # ---- Private ----

    def _make_forwarder(self, device_id: str) -> Callable[[PropResults], Awaitable[None]]:
        async def forwarder(props: PropResults) -> None:
            try:
                self.broadcast({"topic": f"device/{device_id}/properties", "payload": props.model_dump()})
            except Exception:
                log.exception("Error forwarding properties for %s", device_id)

        return forwarder


# ==================== Dependency ====================


def get_devices_service(request: Request) -> DevicesService:
    app_service = request.app.state.app_service
    if app_service.session_service is None:
        raise HTTPException(status_code=503, detail="No active session")
    return app_service.session_service.devices


# ==================== Request models ====================


class SetPropertiesRequest(BaseModel):
    properties: dict[str, Any]


class ExecuteCommandRequest(BaseModel):
    args: list[Any] = []
    kwargs: dict[str, Any] = {}


# ==================== REST ====================


class DeviceSnapshot(BaseModel):
    """One device's identity + interface (or error) at a point in time."""

    id: str
    connected: bool
    interface: DeviceInterface | None = None
    error: str | None = None


class DevicesSnapshot(BaseModel):
    """All devices at a point in time. Shape used by REST + bootstrap."""

    devices: dict[str, DeviceSnapshot]
    count: int


async def snapshot_devices(session: Session) -> DevicesSnapshot:
    """Gather an on-demand snapshot of all devices with their interfaces.

    Shared between the REST endpoint and the session-details bootstrap so the
    frontend gets identical shape from both entry points.
    """
    devices: dict[str, DeviceSnapshot] = {}
    for device_id, handle in session.microscope.devices.items():
        try:
            iface = await handle.interface()
            devices[device_id] = DeviceSnapshot(id=device_id, connected=True, interface=iface)
        except Exception as e:
            log.warning("Failed to get interface for device '%s': %s", device_id, e)
            devices[device_id] = DeviceSnapshot(id=device_id, connected=False, error=str(e))
    return DevicesSnapshot(devices=devices, count=len(devices))


@router.get("/devices")
async def list_devices(service: Annotated[DevicesService, Depends(get_devices_service)]) -> DevicesSnapshot:
    """List all devices with their interfaces."""
    return await snapshot_devices(service.session)


@router.get("/devices/{device_id}/properties")
async def get_device_properties(
    device_id: str,
    service: Annotated[DevicesService, Depends(get_devices_service)],
    props: list[str] | None = None,
) -> dict[str, Any]:
    """Read properties from a device. If ``props`` is omitted, reads all of them."""
    handle = service.session.microscope.devices.get(device_id)
    if not handle:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    if props:
        result = await handle.get_props(*props)
    else:
        iface = await handle.interface()
        result = await handle.get_props(*iface.properties.keys())
    return {"device": device_id, **result.model_dump()}


@router.patch("/devices/{device_id}/properties")
async def set_device_properties(
    device_id: str,
    request: SetPropertiesRequest,
    service: Annotated[DevicesService, Depends(get_devices_service)],
) -> dict[str, Any]:
    try:
        return await service.set_properties(device_id, request.properties)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/devices/{device_id}/commands/{command_name}")
async def execute_device_command(
    device_id: str,
    command_name: str,
    request: ExecuteCommandRequest,
    service: Annotated[DevicesService, Depends(get_devices_service)],
) -> dict[str, Any]:
    try:
        return await service.execute_command(device_id, command_name, request.args, request.kwargs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
