"""HTTP routes for ``session.microscope.devices``."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from vxl_web.protocol.device import DevicesSnapshot, ExecuteCommandRequest, SetPropertiesRequest
from vxl_web.service.session import snapshot_devices

from ._deps import DevicesDep, SessionDep

log = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("")
async def list_devices(svc: SessionDep) -> DevicesSnapshot:
    """List all devices with their interfaces."""
    return await snapshot_devices(svc.session)


@router.get("/{device_id}/properties")
async def get_device_properties(device_id: str, svc: SessionDep, props: list[str] | None = None) -> dict[str, Any]:
    """Read properties from a device. If ``props`` is omitted, reads all of them."""
    handle = svc.session.microscope.devices.get(device_id)
    if not handle:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    if props:
        result = await handle.get_props(*props)
    else:
        iface = await handle.interface()
        result = await handle.get_props(*iface.properties.keys())
    return {"device": device_id, **result.model_dump()}


@router.patch("/{device_id}/properties")
async def set_device_properties(device_id: str, request: SetPropertiesRequest, devices: DevicesDep) -> dict[str, Any]:
    try:
        return await devices.set_properties(device_id, request.properties)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{device_id}/commands/{command_name}")
async def execute_device_command(
    device_id: str,
    command_name: str,
    request: ExecuteCommandRequest,
    devices: DevicesDep,
) -> dict[str, Any]:
    try:
        return await devices.execute(device_id, command_name, request.args, request.kwargs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
