"""Workflow service for acquisition workflow step management.

Handles advancing and reopening workflow steps.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .session import SessionService, get_session_service

workflow_router = APIRouter(prefix="/workflow", tags=["workflow"])
log = logging.getLogger(__name__)


# ==================== Request Models ====================


class ReopenRequest(BaseModel):
    """Request model for reopening a workflow step."""

    step_id: str


# ==================== Workflow Endpoints ====================


@workflow_router.post("/next")
async def workflow_next(
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, str]:
    """Advance to the next workflow step."""
    try:
        service.session.workflow_next()
        service.broadcast({}, with_status=True)
        return {"status": "advanced"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@workflow_router.post("/reopen")
async def workflow_reopen(
    request: ReopenRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, str]:
    """Reopen a workflow step."""
    try:
        service.session.workflow_reopen(request.step_id)
        service.broadcast({}, with_status=True)
        return {"step_id": request.step_id, "status": "reopened"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
