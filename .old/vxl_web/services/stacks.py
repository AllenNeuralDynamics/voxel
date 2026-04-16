"""Stacks service — stack CRUD + plan ordering + stack defaults.

Owns ``/stacks/*`` REST. No WS topics.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from vxl import Session
from vxl.stack import StackOrder

from .ws import BroadcastCallback

log = logging.getLogger(__name__)
router = APIRouter(tags=["stacks"])


# ==================== Service ====================


class StacksService:
    """REST surface for ``session.stacks``. No WS handlers today."""

    topic_prefixes: tuple[str, ...] = ()

    def __init__(self, session: Session, broadcast: BroadcastCallback) -> None:
        self.session = session
        self.broadcast = broadcast

    async def handle_message(self, sender_id: str, topic: str, payload: dict[str, Any]) -> None:
        pass  # no WS topics owned

    async def close(self) -> None:
        """No-op — no subscriptions to tear down."""

    def broadcast_status(self) -> None:
        self.broadcast({}, with_status=True)


# ==================== Dependency ====================


def get_stacks_service(request: Request) -> StacksService:
    app_service = request.app.state.app_service
    if app_service.session_service is None:
        raise HTTPException(status_code=503, detail="No active session")
    return app_service.session_service.stacks


# ==================== Request models ====================


class StackInput(BaseModel):
    x: float
    y: float
    z_start: float
    z_end: float


class AddStacksRequest(BaseModel):
    stacks: list[StackInput]


class StackEditInput(BaseModel):
    stack_id: str
    x: float | None = None
    y: float | None = None
    z_start: float | None = None
    z_end: float | None = None


class EditStacksRequest(BaseModel):
    edits: list[StackEditInput]


class RemoveStacksRequest(BaseModel):
    stack_ids: list[str]


class UpdateOrderRequest(BaseModel):
    stack_order: StackOrder | None = None
    sort_by_profile: bool | None = None
    profile_order: list[str] | None = None


class UpdateDefaultsRequest(BaseModel):
    z_step: float | None = None
    default_z_start: float | None = None
    default_z_end: float | None = None


# ==================== REST — CRUD ====================


@router.get("/stacks")
async def list_stacks(service: Annotated[StacksService, Depends(get_stacks_service)]) -> dict[str, Any]:
    stacks = service.session.stacks
    return {
        "stacks": {s.stack_id: s.model_dump() for s in stacks},
        "count": len(stacks),
    }


@router.post("/stacks")
async def add_stacks(
    request: AddStacksRequest,
    service: Annotated[StacksService, Depends(get_stacks_service)],
) -> dict[str, Any]:
    try:
        added = service.session.stacks.add([s.model_dump() for s in request.stacks])
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    service.broadcast_status()
    return {"stacks": [s.model_dump() for s in added]}


@router.patch("/stacks")
async def edit_stacks(
    request: EditStacksRequest,
    service: Annotated[StacksService, Depends(get_stacks_service)],
) -> dict[str, Any]:
    try:
        edited = service.session.stacks.edit([e.model_dump(exclude_none=True) for e in request.edits])
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    service.broadcast_status()
    return {"stacks": [s.model_dump() for s in edited]}


@router.delete("/stacks")
async def remove_stacks(
    request: RemoveStacksRequest,
    service: Annotated[StacksService, Depends(get_stacks_service)],
) -> dict[str, Any]:
    try:
        removed = [
            service.session.stacks[sid].model_dump()
            for sid in request.stack_ids
            if sid in service.session.stacks
        ]
        service.session.stacks.remove(request.stack_ids)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    service.broadcast_status()
    return {"stacks": removed}


# ==================== REST — Ordering & defaults ====================


@router.put("/stacks/order")
async def update_order(
    request: UpdateOrderRequest,
    service: Annotated[StacksService, Depends(get_stacks_service)],
) -> dict[str, Any]:
    """Update traversal order: stack_order algorithm, sort-by-profile, or profile_order."""
    service.session.stacks.update_order(
        stack_order=request.stack_order,
        sort_by_profile=request.sort_by_profile,
        profile_order=request.profile_order,
    )
    service.broadcast_status()
    plan = service.session.config.plan
    return {
        "stack_order": plan.stack_order,
        "sort_by_profile": plan.sort_by_profile,
        "profile_order": plan.profile_order,
    }


@router.put("/stacks/defaults")
async def update_defaults(
    request: UpdateDefaultsRequest,
    service: Annotated[StacksService, Depends(get_stacks_service)],
) -> dict[str, Any]:
    """Update defaults applied to newly-created stacks (z_step, default z range)."""
    try:
        service.session.stacks.update_defaults(
            z_step=request.z_step,
            default_z_start=request.default_z_start,
            default_z_end=request.default_z_end,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    service.broadcast_status()
    plan = service.session.config.plan
    return {
        "z_step": plan.z_step,
        "default_z_start": plan.default_z_start,
        "default_z_end": plan.default_z_end,
    }
