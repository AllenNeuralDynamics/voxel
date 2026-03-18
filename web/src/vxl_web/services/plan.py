"""Plan service for acquisition plan management.

Handles grid configuration, stack management, tile ordering,
interleaving mode, and profile plan membership.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from vxl.config import GridConfig, Interleaving, TileOrder

from .session import SessionService, get_session_service

plan_router = APIRouter(prefix="/plan", tags=["plan"])
log = logging.getLogger(__name__)


# ==================== Request Models ====================


class TileOrderRequest(BaseModel):
    """Request model for setting tile order."""

    tile_order: TileOrder


class InterleavingRequest(BaseModel):
    """Request model for setting interleaving mode."""

    interleaving: Interleaving


class ReorderProfilesRequest(BaseModel):
    """Request model for reordering profiles in the plan."""

    profile_ids: list[str]


class GridUpdateRequest(BaseModel):
    """Request model for updating grid configuration."""

    x_offset_um: float | None = None
    y_offset_um: float | None = None
    overlap_x: float | None = None
    overlap_y: float | None = None
    force: bool = False


class StackInput(BaseModel):
    """Input model for a single stack."""

    row: int
    col: int
    z_start_um: float
    z_end_um: float


class AddStacksRequest(BaseModel):
    """Request model for adding stacks (bulk)."""

    stacks: list[StackInput]


class StackEditInput(BaseModel):
    """Input model for editing a single stack."""

    row: int
    col: int
    z_start_um: float | None = None
    z_end_um: float | None = None


class EditStacksRequest(BaseModel):
    """Request model for editing stacks (bulk)."""

    edits: list[StackEditInput]


class StackPosition(BaseModel):
    """Position identifier for a stack."""

    row: int
    col: int


class RemoveStacksRequest(BaseModel):
    """Request model for removing stacks (bulk)."""

    positions: list[StackPosition]


# ==================== Plan Endpoints ====================


@plan_router.put("/tile-order")
async def set_tile_order(
    request: TileOrderRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, TileOrder]:
    """Set tile acquisition order."""
    service.session.set_tile_order(request.tile_order)
    service.broadcast({}, with_status=True)
    return {"tile_order": service.session.tile_order}


@plan_router.put("/interleaving")
async def set_interleaving(
    request: InterleavingRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, str]:
    """Set interleaving mode."""
    service.session.set_interleaving(request.interleaving)
    service.broadcast({}, with_status=True)
    return {"interleaving": request.interleaving}


@plan_router.put("/profiles/reorder")
async def reorder_profiles(
    request: ReorderProfilesRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, Any]:
    """Reorder profiles in the acquisition plan."""
    try:
        service.session.reorder_profiles(request.profile_ids)
        service.broadcast({}, with_status=True)
        return {"profile_ids": request.profile_ids, "status": "reordered"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@plan_router.get("/grid")
async def get_grid(service: Annotated[SessionService, Depends(get_session_service)]) -> GridConfig | None:
    """Get current grid configuration for the active profile."""
    return service.session.grid_config


@plan_router.patch("/grid")
async def update_grid(
    request: GridUpdateRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> GridConfig | None:
    """Update grid configuration for the active profile."""
    try:
        if request.x_offset_um is not None and request.y_offset_um is not None:
            service.session.set_grid_offset(request.x_offset_um, request.y_offset_um, force=request.force)
        if request.overlap_x is not None and request.overlap_y is not None:
            service.session.set_overlap(request.overlap_x, request.overlap_y, force=request.force)

        service.broadcast({}, with_status=True)
        return service.session.grid_config
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@plan_router.get("/stacks")
async def list_stacks(service: Annotated[SessionService, Depends(get_session_service)]) -> dict:
    """Get all stacks."""
    return {
        "stacks": [s.model_dump() for s in service.session.stacks],
        "count": len(service.session.stacks),
    }


@plan_router.post("/stacks")
async def add_stacks(
    request: AddStacksRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Add stacks at the specified grid positions (bulk)."""
    try:
        stacks = service.session.add_stacks([s.model_dump() for s in request.stacks])
        service.broadcast({}, with_status=True)
        return {"added": len(stacks), "stacks": [s.model_dump() for s in stacks]}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@plan_router.patch("/stacks")
async def edit_stacks(
    request: EditStacksRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Edit stacks' z parameters (bulk)."""
    try:
        stacks = service.session.edit_stacks([e.model_dump(exclude_none=True) for e in request.edits])
        service.broadcast({}, with_status=True)
        return {"edited": len(stacks), "stacks": [s.model_dump() for s in stacks]}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@plan_router.delete("/stacks")
async def remove_stacks(
    request: RemoveStacksRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Remove stacks (bulk)."""
    try:
        service.session.remove_stacks([p.model_dump() for p in request.positions])
        service.broadcast({}, with_status=True)
        return {"removed": len(request.positions)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
