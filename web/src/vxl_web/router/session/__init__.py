import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from vxl.config import GridConfig
from vxl_web.protocol import AppStatusUpdate
from vxl_web.protocol.session import (
    CreateSessionRequest,
    GridUpdateRequest,
    MetadataSchemaRequest,
    MetadataUpdateRequest,
    OutputUpdateRequest,
    SessionDetails,
)

from . import _acquisition, _devices, _profile, _stacks
from ._deps import AppDep, SessionDep

log = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["session"])

router.include_router(_profile.router)
router.include_router(_stacks.router)
router.include_router(_acquisition.router)
router.include_router(_devices.router)


# ── Lifecycle ──────────────────────────────────────────────


@router.post("")
async def create_session(request: CreateSessionRequest, app: AppDep) -> AppStatusUpdate:
    try:
        await app.create_session(request)
        return await app.get_app_status()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/close")
async def close_session(app: AppDep) -> AppStatusUpdate:
    try:
        await app.close_session()
        return await app.get_app_status()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        log.exception("Failed to close session")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ── Details + metadata ─────────────────────────────────────


@router.get("/details")
async def get_session_details(svc: SessionDep) -> SessionDetails:
    return await svc.get_session_details()


@router.patch("/metadata")
async def update_metadata(request: MetadataUpdateRequest, svc: SessionDep, app: AppDep) -> dict[str, Any]:
    try:
        svc.session.update_metadata(request.metadata)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await app.broadcast_status()
    return {"metadata": svc.session.metadata}


@router.patch("/metadata-schema")
async def update_metadata_schema(request: MetadataSchemaRequest, svc: SessionDep, app: AppDep) -> SessionDetails:
    try:
        svc.session.set_metadata_schema(request.target)
    except (ValueError, TypeError, ImportError, AttributeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await app.broadcast_status()
    return await svc.get_session_details()


# ── Grid ───────────────────────────────────────────────────


@router.get("/grid")
async def get_grid(svc: SessionDep) -> GridConfig:
    return svc.session.config.grid


@router.patch("/grid")
async def update_grid(request: GridUpdateRequest, svc: SessionDep, app: AppDep) -> GridConfig:
    grid = svc.session.config.grid
    try:
        if request.x_offset is not None:
            grid.x_offset = request.x_offset
        if request.y_offset is not None:
            grid.y_offset = request.y_offset
        if request.overlap_x is not None:
            grid.overlap_x = request.overlap_x
        if request.overlap_y is not None:
            grid.overlap_y = request.overlap_y
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await app.broadcast_status()
    return grid


# ── Output ─────────────────────────────────────────────────


@router.get("/output")
async def get_output(svc: SessionDep) -> dict[str, Any]:
    return svc.session.config.output.model_dump(mode="json")


@router.patch("/output")
async def update_output(request: OutputUpdateRequest, svc: SessionDep, app: AppDep) -> dict[str, Any]:
    output = svc.session.config.output
    if request.store_path is not None:
        output.store_path = Path(request.store_path)
    if request.max_level is not None:
        output.max_level = request.max_level  # type: ignore[assignment]
    if request.compression is not None:
        output.compression = request.compression  # type: ignore[assignment]
    await app.broadcast_status()
    return output.model_dump(mode="json")
