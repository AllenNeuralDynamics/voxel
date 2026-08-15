"""Station-scoped REST and WebSocket routes."""

import datetime
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from pydantic import AnyWebsocketUrl, BaseModel, Field, ValidationError
from vxl_records import (
    AcquisitionManifest,
    LogEntry,
    ManifestNotFoundError,
    PresetExistsError,
    PresetNotFoundError,
    PresetRecord,
)

from rigup import PropResults, Result
from vxl.devices.daq.clocked import Signals
from vxl.instrument import (
    AcquisitionRequest,
    ActiveAcquisitionState,
    Instrument,
    InstrumentConfig,
    InstrumentInspection,
    InstrumentPreset,
)
from vxl.instrument.config import (
    ChannelPatch,
    OpticalRoutingPolicy,
    ProfilePatch,
    StencilPatch,
    TaskPatch,
    WriterPatch,
)
from vxl.instrument.metadata import discover_metadata_schema, resolve_metadata_class
from vxl.instrument.traversal import TileOrder
from vxl.preview.protocol import VOXEL_PREVIEW_FRAMING_VERSION
from vxl.station import InstrumentTemplates, SessionInfo, Station, StationFeedView
from vxl.system import StationInfo
from vxlib import ColormapGroup, get_colormap_catalog

station_router = APIRouter(prefix="/stations", tags=["station"])
instrument_router = APIRouter(
    prefix="/stations/{station_id}/sessions/{session_id}/instrument",
    tags=["instrument"],
)


def _get_station(request: Request) -> Station:
    return request.app.state.station


def _get_templates(request: Request) -> InstrumentTemplates:
    return request.app.state.instrument_templates


StationDep = Annotated[Station, Depends(_get_station)]
TemplatesDep = Annotated[InstrumentTemplates, Depends(_get_templates)]


def _get_scoped_station(station_id: UUID, station: StationDep) -> Station:
    if station.config.id != station_id:
        raise HTTPException(status_code=404, detail=f"No station '{station_id}'")
    return station


ScopedStationDep = Annotated[Station, Depends(_get_scoped_station)]


async def _get_instrument(session_id: UUID, station: ScopedStationDep) -> AsyncIterator[Instrument]:
    try:
        async with station.instrument(session_id) as instrument:
            yield instrument
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


InstrumentDep = Annotated[Instrument, Depends(_get_instrument)]


class RealtimeDiscovery(BaseModel):
    state_websocket_url: AnyWebsocketUrl
    preview_websocket_url: AnyWebsocketUrl
    log_websocket_url: AnyWebsocketUrl
    preview_protocol_version: int = Field(ge=1)


class StationDiscovery(BaseModel):
    station: StationInfo
    instruments: dict[str, InstrumentInspection]
    templates: dict[str, InstrumentConfig]
    colormaps: list[ColormapGroup]
    metadata_schemas: dict[str, str]
    realtime: RealtimeDiscovery


class OpenSessionRequest(BaseModel):
    instrument_name: str = Field(min_length=1)


class CreateInstrumentRequest(BaseModel):
    template: str = Field(min_length=1)
    name: str = Field(min_length=1)


class CreatePresetRequest(BaseModel):
    name: str = Field(min_length=1)


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
    target: str


class _DefaultScope(BaseModel):
    include: set[str] | None = None


class _SetProps(BaseModel):
    properties: dict[str, Any]


class _ExecuteCommand(BaseModel):
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class _OpticalRouteOverride(BaseModel):
    route: str


async def _get_preset(station: Station, preset_id: UUID) -> PresetRecord:
    try:
        return await station.records.presets.get(preset_id)
    except PresetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


async def _create_preset(
    station: Station,
    *,
    instrument_name: str,
    name: str,
    value: InstrumentPreset,
) -> PresetRecord:
    preset = PresetRecord(
        id=uuid4(),
        instrument=instrument_name,
        name=name,
        created_at=datetime.datetime.now(tz=datetime.UTC),
        value=value.model_dump(mode="json"),
    )
    try:
        return await station.records.presets.create(preset)
    except PresetExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _parse_preset(value: dict[str, Any]) -> InstrumentPreset:
    try:
        return InstrumentPreset.model_validate(value)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@station_router.get("")
async def list_stations(station: StationDep) -> list[StationInfo]:
    """Return the one Station served by this local web application."""
    return [station.config.info]


@station_router.get("/{station_id}/discovery")
async def get_discovery(
    station_id: UUID,
    request: Request,
    station: StationDep,
    templates: TemplatesDep,
) -> StationDiscovery:
    station = _get_scoped_station(station_id, station)
    return StationDiscovery(
        station=station.config.info,
        instruments=station.discover_instruments(),
        templates=templates.discover(),
        colormaps=get_colormap_catalog(),
        metadata_schemas=discover_metadata_schema(),
        realtime=RealtimeDiscovery(
            state_websocket_url=AnyWebsocketUrl(
                str(request.url_for("station_state_websocket", station_id=str(station_id)))
            ),
            preview_websocket_url=AnyWebsocketUrl(
                str(request.url_for("station_preview_websocket", station_id=str(station_id)))
            ),
            log_websocket_url=AnyWebsocketUrl(
                str(request.url_for("station_logs_websocket", station_id=str(station_id)))
            ),
            preview_protocol_version=VOXEL_PREVIEW_FRAMING_VERSION,
        ),
    )


@station_router.get("/{station_id}/snapshot")
async def get_snapshot(station_id: UUID, station: StationDep) -> StationFeedView:
    station = _get_scoped_station(station_id, station)
    return await station.feed.snapshot()


@station_router.post("/{station_id}/instruments", status_code=201)
async def create_instrument(
    station_id: UUID,
    body: CreateInstrumentRequest,
    station: StationDep,
    templates: TemplatesDep,
) -> InstrumentInspection:
    station = _get_scoped_station(station_id, station)
    try:
        config = templates.get(body.template)
        return await station.create_instrument(body.name, config)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (FileExistsError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@station_router.post("/{station_id}/instruments/{instrument_name}/archive-state")
async def archive_state(station_id: UUID, instrument_name: str, station: StationDep) -> dict[str, str]:
    station = _get_scoped_station(station_id, station)
    try:
        archive = await station.archive_state(instrument_name)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"archived": archive.name}


@station_router.get("/{station_id}/instruments/{instrument_name}/presets")
async def list_presets(station_id: UUID, instrument_name: str, station: StationDep) -> list[PresetRecord]:
    station = _get_scoped_station(station_id, station)
    return await station.records.presets.list(instrument_name)


@station_router.get("/{station_id}/instruments/{instrument_name}/presets/{preset_id}")
async def get_preset(
    station_id: UUID,
    instrument_name: str,
    preset_id: UUID,
    station: StationDep,
) -> PresetRecord:
    station = _get_scoped_station(station_id, station)
    preset = await _get_preset(station, preset_id)
    if preset.instrument != instrument_name:
        raise HTTPException(status_code=404, detail=f"preset not found: {preset_id}")
    return preset


@station_router.delete("/{station_id}/instruments/{instrument_name}/presets/{preset_id}", status_code=204)
async def delete_preset(
    station_id: UUID,
    instrument_name: str,
    preset_id: UUID,
    station: StationDep,
) -> None:
    station = _get_scoped_station(station_id, station)
    preset = await _get_preset(station, preset_id)
    if preset.instrument != instrument_name:
        raise HTTPException(status_code=404, detail=f"preset not found: {preset_id}")
    try:
        await station.records.presets.delete(preset_id)
    except PresetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@station_router.post("/{station_id}/sessions", status_code=201)
async def open_session(station_id: UUID, body: OpenSessionRequest, station: StationDep) -> SessionInfo:
    station = _get_scoped_station(station_id, station)
    try:
        return await station.open_session(body.instrument_name)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@station_router.delete("/{station_id}/sessions/{session_id}", status_code=204)
async def close_session(station_id: UUID, session_id: UUID, station: StationDep) -> None:
    station = _get_scoped_station(station_id, station)
    try:
        await station.close_session(session_id)
    except (RuntimeError, TimeoutError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@station_router.get("/{station_id}/metadata/schema")
async def get_metadata_schema(station_id: UUID, target: str, station: StationDep) -> dict[str, Any]:
    _get_scoped_station(station_id, station)
    try:
        return resolve_metadata_class(target).model_json_schema()
    except (ImportError, AttributeError, TypeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@station_router.get("/{station_id}/acquisitions")
async def list_acquisitions(station_id: UUID, station: StationDep) -> list[AcquisitionManifest]:
    station = _get_scoped_station(station_id, station)
    return await station.records.acquisitions.list_manifests()


@station_router.get("/{station_id}/acquisitions/{acquisition_id}")
async def get_acquisition(station_id: UUID, acquisition_id: UUID, station: StationDep) -> AcquisitionManifest:
    station = _get_scoped_station(station_id, station)
    try:
        return await station.records.acquisitions.get(acquisition_id)
    except ManifestNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@station_router.post("/{station_id}/acquisitions/{acquisition_id}/presets", status_code=201)
async def create_preset_from_acquisition(
    station_id: UUID,
    acquisition_id: UUID,
    body: CreatePresetRequest,
    station: StationDep,
) -> PresetRecord:
    station = _get_scoped_station(station_id, station)
    try:
        acquisition = await station.records.acquisitions.get(acquisition_id)
    except ManifestNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    preset = _parse_preset(acquisition.state_snapshot)
    return await _create_preset(
        station,
        instrument_name=acquisition.instrument,
        name=body.name,
        value=preset,
    )


@station_router.get("/{station_id}/logs")
async def get_logs(
    station_id: UUID,
    station: StationDep,
    after_seq: Annotated[int | None, Query(ge=0)] = None,
    minimum_level: Annotated[int | None, Query(ge=0)] = None,
    node_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 500,
) -> list[LogEntry]:
    station = _get_scoped_station(station_id, station)
    if after_seq is None and minimum_level is None and node_id is None:
        return await station.records.logs.tail(limit=limit)
    return await station.records.logs.query(
        after_seq=after_seq or 0,
        minimum_level=minimum_level,
        node_id=node_id,
        limit=limit,
    )


@station_router.get("/{station_id}/acquisitions/{acquisition_id}/logs")
async def get_acquisition_logs(
    station_id: UUID,
    acquisition_id: UUID,
    station: StationDep,
    after_seq: Annotated[int, Query(ge=0)] = 0,
    minimum_level: Annotated[int | None, Query(ge=0)] = None,
    node_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 500,
) -> list[LogEntry]:
    station = _get_scoped_station(station_id, station)
    try:
        return await station.records.logs.for_acquisition(
            acquisition_id,
            after_seq=after_seq,
            minimum_level=minimum_level,
            node_id=node_id,
            limit=limit,
        )
    except ManifestNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@station_router.websocket("/{station_id}/ws", name="station_state_websocket")
async def station_state_websocket(websocket: WebSocket, station_id: UUID) -> None:
    if websocket.app.state.station.config.id != station_id:
        await websocket.close(code=1008)
        return
    await websocket.app.state.realtime.serve_state(websocket)


@station_router.websocket("/{station_id}/preview/ws", name="station_preview_websocket")
async def station_preview_websocket(websocket: WebSocket, station_id: UUID) -> None:
    if websocket.app.state.station.config.id != station_id:
        await websocket.close(code=1008)
        return
    await websocket.app.state.realtime.serve_preview(websocket)


@station_router.websocket("/{station_id}/logs/ws", name="station_logs_websocket")
async def station_logs_websocket(websocket: WebSocket, station_id: UUID) -> None:
    if websocket.app.state.station.config.id != station_id:
        await websocket.close(code=1008)
        return
    await websocket.app.state.realtime.serve_logs(websocket)


@instrument_router.post("/profile/active")
async def activate_profile(body: _ActivateProfile, instrument: InstrumentDep) -> dict[str, str]:
    return {"active": await instrument.set_active_profile(body.profile_id)}


@instrument_router.post("/presets", status_code=201)
async def create_preset_from_current_state(
    body: CreatePresetRequest,
    station: ScopedStationDep,
    instrument: InstrumentDep,
) -> PresetRecord:
    return await _create_preset(
        station,
        instrument_name=instrument.path.stem,
        name=body.name,
        value=InstrumentPreset.from_state(instrument.state.value),
    )


@instrument_router.post("/presets/{preset_id}/apply", status_code=204)
async def apply_preset(
    preset_id: UUID,
    station: ScopedStationDep,
    instrument: InstrumentDep,
) -> None:
    preset = await _get_preset(station, preset_id)
    instrument_name = instrument.path.stem
    if preset.instrument != instrument_name:
        raise HTTPException(
            status_code=409,
            detail=f"preset '{preset_id}' belongs to '{preset.instrument}', not '{instrument_name}'",
        )
    await instrument.apply_preset(_parse_preset(preset.value))


@instrument_router.patch("/profile", status_code=204)
async def update_profile(patch: ProfilePatch, instrument: InstrumentDep) -> None:
    await instrument.update_profile(patch)


@instrument_router.patch("/profile/sync/{generator_uid}", status_code=204)
async def update_signals(generator_uid: str, signals: Signals, instrument: InstrumentDep) -> None:
    await instrument.update_signals(generator_uid, signals)


@instrument_router.post("/settings/apply", status_code=204)
async def apply_settings(instrument: InstrumentDep) -> None:
    await instrument.apply_settings()


@instrument_router.post("/settings/save", status_code=204)
async def save_settings(instrument: InstrumentDep) -> None:
    await instrument.save_settings()


@instrument_router.post("/optical-routing/apply", status_code=204)
async def apply_optical_routing(instrument: InstrumentDep) -> None:
    await instrument.apply_optical_routing()


@instrument_router.put("/optical-routing/{dimension}/policy", status_code=204)
async def update_optical_routing_policy(
    dimension: str,
    policy: OpticalRoutingPolicy,
    instrument: InstrumentDep,
) -> None:
    await instrument.update_optical_routing_policy(dimension, policy)


@instrument_router.post("/optical-routing/{dimension}/override", status_code=204)
async def override_optical_route(
    dimension: str,
    body: _OpticalRouteOverride,
    instrument: InstrumentDep,
) -> None:
    await instrument.override_optical_route(dimension, body.route)


@instrument_router.post("/default/save", status_code=204)
async def save_as_default(body: _DefaultScope, instrument: InstrumentDep) -> None:
    if body.include is None:
        await instrument.save_as_default()
    else:
        await instrument.save_as_default(body.include)


@instrument_router.post("/default/restore", status_code=204)
async def restore_default(body: _DefaultScope, instrument: InstrumentDep) -> None:
    if body.include is None:
        await instrument.restore_default()
    else:
        await instrument.restore_default(body.include)


@instrument_router.patch("/channels/{channel_id}", status_code=204)
async def update_channel(channel_id: str, patch: ChannelPatch, instrument: InstrumentDep) -> None:
    await instrument.update_channel(channel_id, patch)


@instrument_router.patch("/output", status_code=204)
async def update_output(patch: WriterPatch, instrument: InstrumentDep) -> None:
    await instrument.update_output(patch)


@instrument_router.patch("/stencil", status_code=204)
async def update_stencil(patch: StencilPatch, instrument: InstrumentDep) -> None:
    await instrument.update_stencil(patch)


@instrument_router.patch("/metadata", status_code=204)
async def update_metadata(fields: dict[str, Any], instrument: InstrumentDep) -> None:
    await instrument.update_metadata(**fields)


@instrument_router.put("/metadata/schema", status_code=204)
async def set_metadata_schema(body: _MetadataSchema, instrument: InstrumentDep) -> None:
    await instrument.set_metadata_schema(body.target)


@instrument_router.put("/traversal", status_code=204)
async def set_traversal(body: _Traversal, instrument: InstrumentDep) -> None:
    await instrument.set_traversal(body.order)


@instrument_router.post("/tasks", status_code=204)
async def add_tasks(body: _AddTasks, instrument: InstrumentDep) -> None:
    await instrument.add_tasks(body.xy, profile_ids=body.profile_ids)


@instrument_router.patch("/tasks", status_code=204)
async def update_tasks(body: _UpdateTasks, instrument: InstrumentDep) -> None:
    await instrument.update_tasks(body.patches)


@instrument_router.delete("/tasks", status_code=204)
async def remove_tasks(instrument: InstrumentDep, ids: Annotated[list[str], Query()]) -> None:
    await instrument.remove_tasks(ids)


@instrument_router.post("/preview/start", status_code=204)
async def start_preview(instrument: InstrumentDep) -> None:
    await instrument.start_preview()


@instrument_router.post("/preview/stop", status_code=204)
async def stop_preview(instrument: InstrumentDep) -> None:
    await instrument.stop_preview()


@instrument_router.get("/devices/{device_id}/properties")
async def get_device_properties(
    device_id: str,
    instrument: InstrumentDep,
    props: list[str] | None = None,
) -> PropResults:
    try:
        return await instrument.get_device_properties(device_id, props)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error


@instrument_router.patch("/devices/{device_id}/properties")
async def set_device_properties(device_id: str, body: _SetProps, instrument: InstrumentDep) -> PropResults:
    try:
        return await instrument.set_device_properties(device_id, body.properties)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error


@instrument_router.post("/devices/{device_id}/commands/{command_name}")
async def execute_device_command(
    device_id: str,
    command_name: str,
    body: _ExecuteCommand,
    instrument: InstrumentDep,
) -> Result:
    try:
        return await instrument.execute_device_command(device_id, command_name, body.args, body.kwargs)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error


@instrument_router.post("/acquisition")
async def start_acquisition(body: AcquisitionRequest, instrument: InstrumentDep) -> ActiveAcquisitionState:
    try:
        return await instrument.start_acquisition(body)
    except OSError as error:
        raise HTTPException(status_code=422, detail=f"destination not writable: {error}") from error


@instrument_router.post("/acquisition/stop", status_code=204)
async def stop_acquisition(instrument: InstrumentDep) -> None:
    await instrument.stop_acquisition()


api_router = APIRouter()
api_router.include_router(station_router)
api_router.include_router(instrument_router)


__all__ = ["api_router"]
