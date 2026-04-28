import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from vxl_web.protocol.stacks import (
    AddStacksRequest,
    EditStacksRequest,
    RemoveStacksRequest,
    UpdateDefaultsRequest,
    UpdateOrderRequest,
)

from ._deps import AppDep, SessionDep

log = logging.getLogger(__name__)


router = APIRouter(prefix="/stacks", tags=["stacks"])


@router.get("")
async def list_stacks(svc: SessionDep) -> dict[str, Any]:
    return {
        "stacks": {s.stack_id: s.model_dump() for s in svc.session.stacks},
        "count": len(svc.session.stacks),
    }


@router.post("")
async def add_stacks(request: AddStacksRequest, svc: SessionDep, app: AppDep) -> dict[str, Any]:
    try:
        added = svc.session.stacks.add([s.model_dump() for s in request.stacks])
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await app.broadcast_status()
    return {"stacks": [s.model_dump() for s in added]}


@router.patch("")
async def edit_stacks(request: EditStacksRequest, svc: SessionDep, app: AppDep) -> dict[str, Any]:
    try:
        edited = svc.session.stacks.edit([e.model_dump(exclude_none=True) for e in request.edits])
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await app.broadcast_status()
    return {"stacks": [s.model_dump() for s in edited]}


@router.delete("")
async def remove_stacks(request: RemoveStacksRequest, svc: SessionDep, app: AppDep) -> dict[str, Any]:
    try:
        removed = [svc.session.stacks[sid].model_dump() for sid in request.stack_ids if sid in svc.session.stacks]
        svc.session.stacks.remove(request.stack_ids)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await app.broadcast_status()
    return {"stacks": removed}


@router.put("/order")
async def update_order(request: UpdateOrderRequest, svc: SessionDep, app: AppDep) -> dict[str, Any]:
    """Update traversal: stack_order algorithm, sort-by-profile, or explicit profile_order."""
    svc.session.stacks.update_order(
        stack_order=request.stack_order,
        sort_by_profile=request.sort_by_profile,
        profile_order=request.profile_order,
    )
    await app.broadcast_status()
    plan = svc.session.config.plan
    return {
        "stack_order": plan.stack_order,
        "sort_by_profile": plan.sort_by_profile,
        "profile_order": plan.profile_order,
    }


@router.put("/defaults")
async def update_defaults(request: UpdateDefaultsRequest, svc: SessionDep, app: AppDep) -> dict[str, Any]:
    try:
        svc.session.stacks.update_defaults(
            z_step=request.z_step,
            default_z_start=request.default_z_start,
            default_z_end=request.default_z_end,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await app.broadcast_status()
    plan = svc.session.config.plan
    return {
        "z_step": plan.z_step,
        "default_z_start": plan.default_z_start,
        "default_z_end": plan.default_z_end,
    }
