"""API routers for the rebuilt backend, in one module.

- ``app_router``: the ``VoxelApp`` surface — discover / launch / close, static catalog, and the WS.
- ``instrument_router`` (``/instrument`` prefix): the active ``Instrument`` surface — profile /
  settings / tasks / plan / metadata / devices / preview / acquisition (wired in later increments).

``api_router`` aggregates both. Endpoints map near-1:1 to ``VoxelApp`` / ``Instrument`` methods
(``ProtocolError`` → 422, ``RuntimeError`` → 409).
"""

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from rigup import DeviceHandle, DeviceInterface, PropResults, Result
from vxl.analog_out import AOSignals
from vxl.instrument import (
    AcquisitionRecord,
    AcquisitionRequest,
    ChannelPatch,
    HALConfig,
    ProfilePatch,
    StencilPatch,
    TaskPatch,
    WriterPatch,
)
from vxl.metadata import discover_metadata_schema, resolve_metadata_class
from vxl.system import Remote
from vxl.traversal import TileOrder
from vxlib import ColormapGroup, get_colormap_catalog

from .deps import AppDep, InstrumentDep, LogBufferDep
from .live import AppStatus, InstrumentStatus, LogMessage
from .wire import Client

log = logging.getLogger(__name__)

app_router = APIRouter(tags=["app"])
instrument_router = APIRouter(prefix="/instrument", tags=["instrument"])


# ---- discovery / launch / close (the VoxelApp surface) ----


@app_router.get("/app")
async def get_app_status(app: AppDep) -> AppStatus:
    """App-level presence (active instrument name, or null) — the REST counterpart of the ``app.status`` stream."""
    active = app.active.value
    return AppStatus(active=active.path.stem if active is not None else None)


@app_router.get("/instruments")
async def list_instruments(app: AppDep) -> dict[str, Any]:
    """Existing instruments (fault-tolerant) + shipped templates on this box. No hardware opened."""
    found = app.discover()
    return {
        "instruments": {name: info.model_dump(mode="json") for name, info in found.instruments.items()},
        "templates": {name: cfg.model_dump(mode="json") for name, cfg in found.templates.items()},
    }


@app_router.post("/instruments/{name}/launch")
async def launch(name: str, app: AppDep) -> dict[str, str]:
    """Open ``<name>.voxel`` and make it active. 404 if missing, 409 if one is already active.

    The live feed follows from ``VoxelApp.active`` (wired in the lifespan's ``AppFeed``) — no feed work here.
    """
    try:
        instrument = await app.launch(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"launched": instrument.path.stem}


@app_router.post("/templates/{template}/launch")
async def launch_template(template: str, app: AppDep, name: str | None = None) -> dict[str, str]:
    """Instantiate ``template`` (``name`` defaults to the template's) into a new instrument, then launch it."""
    try:
        instrument = await app.launch_template(template, name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except (FileExistsError, RuntimeError) as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"launched": instrument.path.stem}


@app_router.post("/close")
async def close(app: AppDep) -> dict[str, bool]:
    """Close the active instrument (no-op if none); its feed detaches via ``VoxelApp.active``."""
    await app.close()
    return {"closed": True}


# ---- static catalog (no instrument required) ----


@app_router.get("/catalog/colormaps")
async def list_colormaps() -> list[ColormapGroup]:
    return get_colormap_catalog()


@app_router.get("/catalog/remotes")
async def list_remotes(app: AppDep) -> dict[str, Remote]:
    """Configured object stores: name → connection + selectable roots (from ``System.remotes``).
    A local run targets no remote."""
    return app.remotes


@app_router.get("/catalog/metadata/schemas")
async def list_metadata_schemas() -> dict[str, Any]:
    return {"schemas": discover_metadata_schema()}


@app_router.get("/catalog/metadata/schema")
async def get_metadata_schema(target: str) -> dict[str, Any]:
    try:
        return resolve_metadata_class(target).model_json_schema()
    except (ImportError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ---- WebSocket (msgpack [topic, body] over MsgBus) ----


@app_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Register the peer on the bus and relay broadcasts until disconnect. Clients hydrate via REST, not here."""
    bus = websocket.app.state.bus
    await websocket.accept()
    client_id = str(uuid.uuid4())
    client = Client(client_id, websocket)
    await client.start()
    await bus.add_client(client)
    try:
        while True:
            await bus.dispatch_inbound(client_id, await websocket.receive_bytes())
    except WebSocketDisconnect:
        log.debug("client %s disconnected", client_id)
    finally:
        await bus.remove_client(client)


@app_router.get("/logs")
async def get_logs(logs: LogBufferDep) -> list[LogMessage]:
    """Recent log backlog for (re)connect hydration; clients merge it with the live ``logs`` stream by ``seq``."""
    return list(logs)


# ---- active-instrument read + edit (the Instrument surface) ----


class _ActivateProfile(BaseModel):
    profile_id: str


class _AddTasks(BaseModel):
    xy: list[tuple[float, float]]
    profile_ids: list[str] | None = None


class _UpdateTasks(BaseModel):
    patches: dict[str, TaskPatch]


class _Traversal(BaseModel):
    order: TileOrder


class _MetadataSchema(BaseModel):
    target: str  # dotted path or registered schema name


class DeviceSnapshot(BaseModel):
    """One device's identity + introspected interface, or the error that introspection raised."""

    id: str
    connected: bool
    interface: DeviceInterface | None = None
    error: str | None = None


class _SetProps(BaseModel):
    properties: dict[str, Any]


class _ExecuteCommand(BaseModel):
    args: list[Any] = []
    kwargs: dict[str, Any] = {}


@instrument_router.get("")
async def get_status(inst: InstrumentDep) -> InstrumentStatus:
    """The current whole-instrument snapshot — same shape as the ``instrument.status`` WS topic."""
    return InstrumentStatus(
        mode=inst.mode.value,
        active_profile_id=inst.active_profile_id.value,
        preview_epoch=inst.preview_epoch.value,
        fov=await inst.fov.get(),
        state=inst.state.value,
        task_tiles=inst.task_tiles.value,
    )


@instrument_router.get("/hardware")
async def get_hardware(inst: InstrumentDep) -> HALConfig:
    """The immutable hardware blueprint (rig + stage + detection/illumination paths).

    Separate from the editable bench in ``GET /instrument`` (``InstrumentState``): the UI needs the HAL
    config for preview frame rotation (``detection[*].rotation_deg``), device→role mapping, and stage axes.
    """
    return inst.hal.config


@instrument_router.post("/profile/active")
async def activate_profile(body: _ActivateProfile, inst: InstrumentDep) -> dict[str, str]:
    return {"active": await inst.set_active_profile(body.profile_id)}


@instrument_router.patch("/profile", status_code=204)
async def update_profile(patch: ProfilePatch, inst: InstrumentDep) -> None:
    await inst.update_profile(patch)


@instrument_router.patch("/profile/sync/{ao_uid}", status_code=204)
async def update_ao_signals(ao_uid: str, signals: AOSignals, inst: InstrumentDep) -> None:
    await inst.update_ao_signals(ao_uid, signals)


@instrument_router.post("/settings/apply", status_code=204)
async def apply_settings(inst: InstrumentDep) -> None:
    await inst.apply_settings()


@instrument_router.post("/settings/save", status_code=204)
async def save_settings(inst: InstrumentDep) -> None:
    await inst.save_settings()


@instrument_router.patch("/channels/{channel_id}", status_code=204)
async def update_channel(channel_id: str, patch: ChannelPatch, inst: InstrumentDep) -> None:
    await inst.update_channel(channel_id, patch)


@instrument_router.patch("/output", status_code=204)
async def update_output(patch: WriterPatch, inst: InstrumentDep) -> None:
    await inst.update_output(patch)


@instrument_router.patch("/stencil", status_code=204)
async def update_stencil(patch: StencilPatch, inst: InstrumentDep) -> None:
    await inst.update_stencil(patch)


@instrument_router.patch("/metadata", status_code=204)
async def update_metadata(fields: dict[str, Any], inst: InstrumentDep) -> None:
    await inst.update_metadata(**fields)


@instrument_router.put("/metadata/schema", status_code=204)
async def set_metadata_schema(body: _MetadataSchema, inst: InstrumentDep) -> None:
    await inst.set_metadata_schema(body.target)


@instrument_router.put("/traversal", status_code=204)
async def set_traversal(body: _Traversal, inst: InstrumentDep) -> None:
    await inst.set_traversal(body.order)


@instrument_router.post("/tasks", status_code=204)
async def add_tasks(body: _AddTasks, inst: InstrumentDep) -> None:
    await inst.add_tasks(body.xy, profile_ids=body.profile_ids)


@instrument_router.patch("/tasks", status_code=204)
async def update_tasks(body: _UpdateTasks, inst: InstrumentDep) -> None:
    await inst.update_tasks(body.patches)


@instrument_router.delete("/tasks", status_code=204)
async def remove_tasks(inst: InstrumentDep, ids: Annotated[list[str], Query()]) -> None:

    await inst.remove_tasks(ids)


@instrument_router.post("/preview/start", status_code=204)
async def start_preview(inst: InstrumentDep) -> None:
    await inst.start_preview()


@instrument_router.post("/preview/stop", status_code=204)
async def stop_preview(inst: InstrumentDep) -> None:
    await inst.stop_preview()


# viewport / levels / colormap are WS commands (`preview.update`), not REST — they need sender-excluded
# multi-client echo (see InstrumentFeed). start/stop stay REST: they flip `mode`, which echoes via status.


def _device_or_404(devices: dict[str, DeviceHandle], device_id: str) -> DeviceHandle:
    handle = devices.get(device_id)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return handle


@instrument_router.get("/devices")
async def list_devices(inst: InstrumentDep) -> dict[str, DeviceSnapshot]:
    """Each device's interface. Per-device fault tolerance: a failed introspection is reported, not raised."""
    snapshot: dict[str, DeviceSnapshot] = {}
    for device_id, handle in inst.hal.devices.items():
        try:
            iface = await handle.interface()
        except Exception as e:
            log.warning("device '%s' interface introspection failed: %s", device_id, e)
            snapshot[device_id] = DeviceSnapshot(id=device_id, connected=False, error=str(e))
        else:
            snapshot[device_id] = DeviceSnapshot(id=device_id, connected=True, interface=iface)
    return snapshot


@instrument_router.get("/devices/{device_id}/properties")
async def get_device_properties(device_id: str, inst: InstrumentDep, props: list[str] | None = None) -> PropResults:
    """Read ``props`` (all of the device's properties if omitted)."""
    handle = _device_or_404(inst.hal.devices, device_id)
    names = props or list((await handle.interface()).properties.keys())
    return await handle.props.get(*names)


@instrument_router.patch("/devices/{device_id}/properties")
async def set_device_properties(device_id: str, body: _SetProps, inst: InstrumentDep) -> PropResults:
    """Set properties; the returned ``PropResults`` carries per-property accept/reject. Subscribers get
    a ``device.props.update`` push via the feed (``props.set`` notifies)."""
    handle = _device_or_404(inst.hal.devices, device_id)
    return await handle.props.set(**body.properties)


@instrument_router.post("/devices/{device_id}/commands/{cmd_name}")
async def execute_device_command(device_id: str, cmd_name: str, body: _ExecuteCommand, inst: InstrumentDep) -> Result:
    handle = _device_or_404(inst.hal.devices, device_id)
    return await handle.run_command(cmd_name, *body.args, **body.kwargs)


@instrument_router.post("/acquisition")
async def start_acquisition(body: AcquisitionRequest, inst: InstrumentDep) -> AcquisitionRecord:
    """Launch the requested acquisition and return its record once the run has started.

    The synchronous preflight writes a marker to the destination; an unwritable target raises ``OSError``
    here (mapped to 422) before any capture. Progress streams on the ``acquisition.progress`` WS topic.
    """
    try:
        return await inst.start_acquisition(body)
    except OSError as e:
        raise HTTPException(status_code=422, detail=f"destination not writable: {e}") from e


@instrument_router.post("/acquisition/stop", status_code=204)
async def stop_acquisition(inst: InstrumentDep) -> None:
    await inst.stop_acquisition()


api_router = APIRouter()
api_router.include_router(app_router)
api_router.include_router(instrument_router)
