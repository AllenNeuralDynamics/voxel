"""Acquisition service for acquisition config and stack management.

Handles grid configuration, stack management, tile ordering,
interleaving mode, profile ordering, and storage settings.
"""

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from ome_zarr_writer.types import Compression, ScaleLevel
from pydantic import BaseModel

from vxl.config import GridConfig
from vxl.stack import StackOrder

from .session import SessionService, get_session_service

acq_router = APIRouter(prefix="/acq", tags=["acq"])
log = logging.getLogger(__name__)


# ==================== Request Models ====================


class StackOrderRequest(BaseModel):
    """Request model for setting stack order."""

    stack_order: StackOrder


class SortByProfileRequest(BaseModel):
    """Request model for setting sort-by-profile mode."""

    sort_by_profile: bool


class ReorderProfilesRequest(BaseModel):
    """Request model for reordering profiles."""

    profile_ids: list[str]


class GridUpdateRequest(BaseModel):
    """Request model for updating grid configuration. All positions in µm."""

    x_offset: float | None = None
    y_offset: float | None = None
    overlap_x: float | None = None
    overlap_y: float | None = None
    default_z_start: float | None = None
    default_z_end: float | None = None


class StackInput(BaseModel):
    """Input model for a single stack. All positions in µm."""

    x: float
    y: float
    z_start: float
    z_end: float


class AddStacksRequest(BaseModel):
    """Request model for adding stacks (bulk)."""

    stacks: list[StackInput]


class StackEditInput(BaseModel):
    """Input model for editing a single stack. All positions in µm."""

    stack_id: str
    x: float | None = None
    y: float | None = None
    z_start: float | None = None
    z_end: float | None = None


class EditStacksRequest(BaseModel):
    """Request model for editing stacks (bulk)."""

    edits: list[StackEditInput]


class RemoveStacksRequest(BaseModel):
    """Request model for removing stacks (bulk)."""

    stack_ids: list[str]


class StorageSettingsRequest(BaseModel):
    """Request model for updating storage settings."""

    store_path: str | None = None
    max_level: int | None = None
    compression: str | None = None
    batch_z_shards: int | None = None
    target_shard_gb: float | None = None


# ==================== Settings Endpoints ====================


@acq_router.get("/storage")
async def get_storage(
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Get current storage settings."""
    s = service.session.storage
    return {
        "store_path": str(s.store_path) if s.store_path else None,
        "max_level": s.max_level,
        "compression": s.compression,
        "batch_z_shards": s.batch_z_shards,
        "target_shard_gb": s.target_shard_gb,
    }


@acq_router.patch("/storage")
async def update_storage(
    request: StorageSettingsRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Update storage settings."""
    s = service.session.storage
    if request.store_path is not None:
        s.store_path = Path(request.store_path)
    if request.max_level is not None:
        s.max_level = ScaleLevel(request.max_level)
    if request.compression is not None:
        s.compression = Compression(request.compression)
    if request.batch_z_shards is not None:
        s.batch_z_shards = request.batch_z_shards
    if request.target_shard_gb is not None:
        s.target_shard_gb = request.target_shard_gb
    service.session.save()
    service.broadcast({}, with_status=True)
    return {
        "store_path": str(s.store_path) if s.store_path else None,
        "max_level": s.max_level,
        "compression": s.compression,
        "batch_z_shards": s.batch_z_shards,
        "target_shard_gb": s.target_shard_gb,
    }


# ==================== Acquisition Control ====================


@acq_router.post("/start")
async def start_acquisition(
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Start acquisition for all pending stacks."""
    pending = [s for s in service.session.stacks.values() if s.status == "planned"]
    if not pending:
        raise HTTPException(status_code=400, detail="No planned stacks to acquire")
    service.start_acquisition()
    return {"status": "started", "pending": len(pending)}


@acq_router.post("/start/{stack_id}")
async def start_stack_acquisition(
    stack_id: str,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Start acquisition for a single stack."""
    stack = service.session.stacks.get(stack_id)
    if stack is None:
        raise HTTPException(status_code=404, detail=f"Stack {stack_id} not found")
    if stack.status != "planned":
        raise HTTPException(status_code=400, detail=f"Stack {stack_id} has status {stack.status}, expected planned")
    service.start_acquisition(stack_id)
    return {"status": "started", "stack_id": stack_id}


@acq_router.post("/stop")
async def stop_acquisition(
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Stop the current acquisition."""
    service.session.stop_acquisition()
    return {"status": "stopped"}


# ==================== Ordering Endpoints ====================


@acq_router.put("/stack-order")
async def set_stack_order(
    request: StackOrderRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, str]:
    """Set stack ordering strategy."""
    service.session.set_stack_order(request.stack_order)
    service.broadcast({}, with_status=True)
    return {"stack_order": service.session.stack_order}


@acq_router.put("/sort-by-profile")
async def set_sort_by_profile(
    request: SortByProfileRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, bool]:
    """Set sort-by-profile mode."""
    service.session.set_sort_by_profile(request.sort_by_profile)
    service.broadcast({}, with_status=True)
    return {"sort_by_profile": request.sort_by_profile}


@acq_router.put("/profiles/reorder")
async def reorder_profiles(
    request: ReorderProfilesRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, Any]:
    """Reorder profiles in the acquisition config."""
    try:
        service.session.reorder_profiles(request.profile_ids)
        service.broadcast({}, with_status=True)
        return {"profile_ids": request.profile_ids, "status": "reordered"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ==================== Grid Endpoints ====================


@acq_router.get("/grid")
async def get_grid(service: Annotated[SessionService, Depends(get_session_service)]) -> GridConfig:
    """Get current grid configuration."""
    return service.session.grid


@acq_router.patch("/grid")
async def update_grid(
    request: GridUpdateRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> GridConfig:
    """Update grid configuration."""
    try:
        service.session.update_grid(
            x_offset=request.x_offset,
            y_offset=request.y_offset,
            overlap_x=request.overlap_x,
            overlap_y=request.overlap_y,
        )
        if request.default_z_start is not None and request.default_z_end is not None:
            service.session.set_default_z_range(request.default_z_start, request.default_z_end)

        service.broadcast({}, with_status=True)
        return service.session.grid
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ==================== Stack Endpoints ====================


@acq_router.get("/stacks")
async def list_stacks(service: Annotated[SessionService, Depends(get_session_service)]) -> dict:
    """Get all stacks."""
    return {
        "stacks": {sid: s.model_dump() for sid, s in service.session.stacks.items()},
        "count": len(service.session.stacks),
    }


@acq_router.post("/stacks")
async def add_stacks(
    request: AddStacksRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Add stacks at the specified grid positions (bulk)."""
    try:
        stacks = service.session.add_stacks([s.model_dump() for s in request.stacks])
        service.broadcast({}, with_status=True)
        return {"stacks": [s.model_dump() for s in stacks]}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@acq_router.patch("/stacks")
async def edit_stacks(
    request: EditStacksRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Edit stacks' z parameters (bulk)."""
    try:
        stacks = service.session.edit_stacks([e.model_dump(exclude_none=True) for e in request.edits])
        service.broadcast({}, with_status=True)
        return {"stacks": [s.model_dump() for s in stacks]}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@acq_router.delete("/stacks")
async def remove_stacks(
    request: RemoveStacksRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Remove stacks (bulk). Returns the removed stacks for undo support."""
    try:
        removed = [s.model_dump() for sid in request.stack_ids if (s := service.session.stacks.get(sid))]
        service.session.remove_stacks(request.stack_ids)
        service.broadcast({}, with_status=True)
        return {"stacks": removed}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
