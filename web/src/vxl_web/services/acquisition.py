"""Acquisition service — REST control for ``session.acquisition``.

Launches acquisition as a background task. Progress broadcasts are driven by
subscribing to ``session.acquisition.progress`` (a Cell[StackProgress | None])
and emitting each update as a ``stack/progress`` event. No manual broadcast
orchestration — the engine is the source of truth.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from vxl import Session
from vxl.stack import StackProgress, StackStatus
from vxlib import fire_and_forget

from .ws import BroadcastCallback

log = logging.getLogger(__name__)
router = APIRouter(tags=["acquisition"])


# ==================== Service ====================


class AcquisitionService:
    """Subscribes to engine progress; launches acquisitions as background tasks."""

    topic_prefixes: tuple[str, ...] = ()

    def __init__(self, session: Session, broadcast: BroadcastCallback) -> None:
        self.session = session
        self.broadcast = broadcast
        self._unsub_progress = session.acquisition.progress.subscribe(self._on_progress)

    async def handle_message(self, sender_id: str, topic: str, payload: dict[str, Any]) -> None:
        pass

    async def close(self) -> None:
        self._unsub_progress()

    # ---- Launchers ----

    def start_single(self, stack_id: str) -> None:
        fire_and_forget(self.session.acquire_stack(stack_id), log=log)

    def start_all(self) -> None:
        fire_and_forget(self.session.acquire_all(), log=log)

    # ---- Progress subscription ----

    async def _on_progress(self, progress: StackProgress | None) -> None:
        if progress is None:
            return
        self.broadcast({"topic": "stack/progress", "payload": progress.model_dump(mode="json")})


# ==================== Dependency ====================


def get_acquisition_service(request: Request) -> AcquisitionService:
    app_service = request.app.state.app_service
    if app_service.session_service is None:
        raise HTTPException(status_code=503, detail="No active session")
    return app_service.session_service.acquisition


# ==================== REST ====================


class StartStackRequest(BaseModel):
    stack_id: str | None = None  # unused — pass via path param


@router.post("/acquisition/start")
async def start_acquisition(
    service: Annotated[AcquisitionService, Depends(get_acquisition_service)],
) -> dict[str, Any]:
    """Start acquisition for all PLANNED stacks."""
    pending = [s for s in service.session.stacks if s.status == StackStatus.PLANNED]
    if not pending:
        raise HTTPException(status_code=400, detail="No planned stacks to acquire")
    service.start_all()
    return {"status": "started", "pending": len(pending)}


@router.post("/acquisition/start/{stack_id}")
async def start_stack_acquisition(
    stack_id: str,
    service: Annotated[AcquisitionService, Depends(get_acquisition_service)],
) -> dict[str, Any]:
    """Start acquisition for one stack."""
    if stack_id not in service.session.stacks:
        raise HTTPException(status_code=404, detail=f"Stack {stack_id} not found")
    stack = service.session.stacks[stack_id]
    if stack.status != StackStatus.PLANNED:
        raise HTTPException(
            status_code=400,
            detail=f"Stack {stack_id} has status {stack.status}, expected planned",
        )
    service.start_single(stack_id)
    return {"status": "started", "stack_id": stack_id}


@router.post("/acquisition/stop")
async def stop_acquisition() -> dict[str, str]:
    """Stop the current acquisition (best-effort — not always supported by the engine)."""
    log.warning("Acquisition stop requested — not currently supported by the engine")
    return {"status": "stop-requested"}
