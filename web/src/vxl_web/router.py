"""API routers for the rebuilt backend, in one module.

- ``app_router``: the ``VoxelApp`` surface — discovery / launch / close, acquisition history, and the WS.
- ``instrument_router`` (``/instrument`` prefix): the active ``Instrument`` surface — profile /
  settings / tasks / plan / metadata / devices / preview / acquisition (wired in later increments).

``api_router`` aggregates both. Endpoints map near-1:1 to ``VoxelApp`` / ``Instrument`` methods
(``OperationRejectedError`` → 422, ``InstrumentBusyError`` → 409).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket
from pydantic import AnyWebsocketUrl, BaseModel
from vxl_catalog import AcquisitionManifest, ManifestNotFoundError

from rigup import PropResults, Result
from vxl.daq.clocked import Signals
from vxl.instrument import (
    AcquisitionRequest,
    ActiveAcquisitionState,
    DeviceSnapshot,
    InstrumentConfig,
    InstrumentInspection,
)
from vxl.instrument.feed import InstrumentView
from vxl.instrument.state import (
    ChannelPatch,
    InstrumentDefaults,
    OpticalRoutingPolicy,
    ProfilePatch,
    StencilPatch,
    TaskPatch,
    WriterPatch,
)
from vxl.instrument.topology import HALConfig
from vxl.instrument.traversal import TileOrder
from vxl.metadata import discover_metadata_schema, resolve_metadata_class
from vxl.preview.protocol import DELIVERY_FRAMING_VERSION
from vxl.system import Remote, StationInfo
from vxlib import ColormapGroup, get_colormap_catalog

from .adapter import AppStatus, LogMessage
from .deps import AppDep, InstrumentDep, LogBufferDep

app_router = APIRouter(tags=["app"])
instrument_router = APIRouter(prefix="/instrument", tags=["instrument"])


# ---- discovery / launch / close (the VoxelApp surface) ----


class PreviewDiscovery(BaseModel):
    """Resolved preview connection."""

    websocket_url: AnyWebsocketUrl
    protocol_version: int


class AppDiscovery(BaseModel):
    """Bounded resources a client needs to discover and configure this Voxel application."""

    station: StationInfo
    instruments: dict[str, InstrumentInspection]
    templates: dict[str, InstrumentConfig]
    remotes: dict[str, Remote]
    colormaps: list[ColormapGroup]
    metadata_schemas: dict[str, str]
    preview: PreviewDiscovery


@app_router.get("/app")
async def get_app_status(app: AppDep) -> AppStatus:
    """App-level presence (active instrument name, or null) — the REST counterpart of the ``app.status`` stream."""
    active = app.active.value
    return AppStatus(active=active.path.stem if active is not None else None)


@app_router.get("/discovery")
async def get_discovery(request: Request, app: AppDep) -> AppDiscovery:
    """Return the bounded application resources needed to initialize a client."""
    found = app.discover()
    return AppDiscovery(
        station=app.station.info,
        instruments=found.instruments,
        templates=found.templates,
        remotes=app.remotes,
        colormaps=get_colormap_catalog(),
        metadata_schemas=discover_metadata_schema(),
        preview=PreviewDiscovery(
            websocket_url=AnyWebsocketUrl(str(request.url_for("preview_websocket"))),
            protocol_version=DELIVERY_FRAMING_VERSION,
        ),
    )


@app_router.post("/instruments/{name}/launch")
async def launch(name: str, app: AppDep) -> dict[str, str]:
    """Open ``<name>.voxel`` and make it active. 404 if missing, 409 if one is already active.

    The web adapter follows ``VoxelApp.active`` and attaches to the instrument feed — no feed work here.
    """
    try:
        instrument = await app.launch(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"launched": instrument.path.stem}


@app_router.post("/instruments/{name}/archive-bench")
async def archive_bench(name: str, app: AppDep) -> dict[str, str]:
    """Archive ``bench.json`` under the next available backup name.

    404 if the instrument or its bench is missing; 409 if the instrument is active.
    """
    try:
        archive = app.archive_bench(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"archived": archive.name}


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


# ---- resource details and acquisition history (no active instrument required) ----


@app_router.get("/metadata/schema")
async def get_metadata_schema(target: str) -> dict[str, Any]:
    try:
        return resolve_metadata_class(target).model_json_schema()
    except (ImportError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app_router.get("/acquisitions")
async def list_acquisitions(app: AppDep) -> list[AcquisitionManifest]:
    """Return acquisition manifests from newest to oldest."""
    return await app.catalog.list_manifests()


@app_router.get("/acquisitions/{acquisition_id}")
async def get_acquisition(acquisition_id: uuid.UUID, app: AppDep) -> AcquisitionManifest:
    """Return one durable acquisition manifest."""
    try:
        return await app.catalog.get(acquisition_id)
    except ManifestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ---- WebSocket (msgpack [topic, body] over MsgBus) ----


@app_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Register the peer on the bus and relay broadcasts until disconnect. Clients hydrate via REST, not here."""
    await websocket.app.state.vxl.serve(websocket)


@app_router.websocket("/preview/ws", name="preview_websocket")
async def preview_websocket_endpoint(websocket: WebSocket) -> None:
    """Deliver complete opaque VXPD packets over a dedicated latest-only connection."""
    await websocket.app.state.vxl.serve_preview(websocket)


@app_router.get("/logs")
async def get_logs(logs: LogBufferDep) -> list[LogMessage]:
    """Recent log backlog for (re)connect hydration; clients merge it with ``app.logs`` by ``seq``."""
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


class _DefaultScope(BaseModel):
    include: set[str] | None = None  # None → all promotable baseline fields


class _SetProps(BaseModel):
    properties: dict[str, Any]


class _ExecuteCommand(BaseModel):
    args: list[Any] = []
    kwargs: dict[str, Any] = {}


class _OpticalRouteOverride(BaseModel):
    route: str


@instrument_router.get("")
async def get_status(inst: InstrumentDep) -> InstrumentView:
    """Complete cached instrument view and cursor for continuing on ``instrument.feed.updates``."""
    return inst.feed.view()


@instrument_router.get("/hardware")
async def get_hardware(inst: InstrumentDep) -> HALConfig:
    """The immutable hardware blueprint (rig + stage + detection/illumination paths).

    Separate from the editable bench in ``GET /instrument`` (``InstrumentState``): the UI needs the HAL
    config for preview frame rotation (``detection[*].rotation_deg``), device→role mapping, and stage axes.
    """
    return inst.hardware_config


@instrument_router.get("/default")
async def get_default(inst: InstrumentDep) -> InstrumentDefaults:
    """The on-disk baseline (``config.yaml`` ``default``); retained as a compatibility endpoint."""
    return inst.default.value


@instrument_router.post("/profile/active")
async def activate_profile(body: _ActivateProfile, inst: InstrumentDep) -> dict[str, str]:
    return {"active": await inst.set_active_profile(body.profile_id)}


@instrument_router.patch("/profile", status_code=204)
async def update_profile(patch: ProfilePatch, inst: InstrumentDep) -> None:
    await inst.update_profile(patch)


@instrument_router.patch("/profile/sync/{generator_uid}", status_code=204)
async def update_signals(generator_uid: str, signals: Signals, inst: InstrumentDep) -> None:
    await inst.update_signals(generator_uid, signals)


@instrument_router.post("/settings/apply", status_code=204)
async def apply_settings(inst: InstrumentDep) -> None:
    await inst.apply_settings()


@instrument_router.post("/settings/save", status_code=204)
async def save_settings(inst: InstrumentDep) -> None:
    await inst.save_settings()


@instrument_router.post("/optical-routing/apply", status_code=204)
async def apply_optical_routing(inst: InstrumentDep) -> None:
    await inst.apply_optical_routing()


@instrument_router.put("/optical-routing/{dimension}/policy", status_code=204)
async def update_optical_routing_policy(
    dimension: str,
    policy: OpticalRoutingPolicy,
    inst: InstrumentDep,
) -> None:
    await inst.update_optical_routing_policy(dimension, policy)


@instrument_router.post("/optical-routing/{dimension}/override", status_code=204)
async def override_optical_route(dimension: str, body: _OpticalRouteOverride, inst: InstrumentDep) -> None:
    await inst.override_optical_route(dimension, body.route)


@instrument_router.post("/default/save", status_code=204)
async def save_as_default(body: _DefaultScope, inst: InstrumentDep) -> None:
    """Persist the live bench's baseline fields into ``config.yaml``'s ``default`` (all, or ``include``)."""
    if body.include is None:
        await inst.save_as_default()
    else:
        await inst.save_as_default(body.include)


@instrument_router.post("/default/restore", status_code=204)
async def restore_default(body: _DefaultScope, inst: InstrumentDep) -> None:
    """Reset the live bench's baseline fields from ``config.yaml``'s ``default`` (all, or ``include``)."""
    if body.include is None:
        await inst.restore_default()
    else:
        await inst.restore_default(body.include)


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


# Viewport and levels use the bidirectional `instrument.preview` topic, not REST — they need sender-excluded
# Multi-client preview state uses the web adapter. Start/stop remain REST controls.


@instrument_router.get("/devices")
async def list_devices(inst: InstrumentDep) -> dict[str, DeviceSnapshot]:
    """Each device's interface. Per-device fault tolerance: a failed introspection is reported, not raised."""
    return await inst.inspect_devices()


@instrument_router.get("/devices/{device_id}/properties")
async def get_device_properties(device_id: str, inst: InstrumentDep, props: list[str] | None = None) -> PropResults:
    """Read ``props`` (all of the device's properties if omitted)."""
    try:
        return await inst.get_device_properties(device_id, props)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error


@instrument_router.patch("/devices/{device_id}/properties")
async def set_device_properties(device_id: str, body: _SetProps, inst: InstrumentDep) -> PropResults:
    """Set properties and return per-property accept/reject results; the feed publishes the accepted update."""
    try:
        return await inst.set_device_properties(device_id, body.properties)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error


@instrument_router.post("/devices/{device_id}/commands/{cmd_name}")
async def execute_device_command(device_id: str, cmd_name: str, body: _ExecuteCommand, inst: InstrumentDep) -> Result:
    try:
        return await inst.execute_device_command(device_id, cmd_name, body.args, body.kwargs)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error


@instrument_router.get("/acquisition")
async def get_active_acquisition(inst: InstrumentDep) -> ActiveAcquisitionState | None:
    """Return the retained state for the current run, or ``None`` while the instrument is idle."""
    return inst.acquisition.value


@instrument_router.post("/acquisition")
async def start_acquisition(body: AcquisitionRequest, inst: InstrumentDep) -> ActiveAcquisitionState:
    """Launch the requested acquisition and return its retained state once the run has started.

    The synchronous preflight writes a marker to the destination; an unwritable target raises ``OSError``
    here (mapped to 422) before any capture. State streams through ``instrument.feed.updates``.
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
