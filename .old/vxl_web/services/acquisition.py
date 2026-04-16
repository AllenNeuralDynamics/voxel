"""Acquisition service — REST control for ``session.acquisition``.

Launches acquisition as a background task and broadcasts progress over WS.
No WS topics owned (progress updates go out as broadcasts, not responses).
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from vxl import Session
from vxl.stack import StackStatus
from vxlib import fire_and_forget

from .ws import BroadcastCallback

log = logging.getLogger(__name__)
router = APIRouter(tags=["acquisition"])


# ==================== Service ====================


class AcquisitionService:
    """Wraps ``session.acquire_stack`` / ``acquire_all`` as fire-and-forget background tasks."""

    topic_prefixes: tuple[str, ...] = ()

    def __init__(self, session: Session, broadcast: BroadcastCallback) -> None:
        self.session = session
        self.broadcast = broadcast

    async def handle_message(self, sender_id: str, topic: str, payload: dict[str, Any]) -> None:
        pass

    async def close(self) -> None:
        """No-op — acquisition background tasks are fire-and-forget and die with the event loop."""

    # ---- Launchers ----

    def start_single(self, stack_id: str) -> None:
        fire_and_forget(self._run_single(stack_id), log=log)

    def start_all(self) -> None:
        fire_and_forget(self._run_all(), log=log)

    # ---- Background coroutines ----

    async def _run_single(self, stack_id: str) -> None:
        try:
            self.broadcast(
                {"topic": "acq/progress", "payload": {"status": "started", "stack_id": stack_id}},
                with_status=True,
            )
            result = await self.session.acquire_stack(stack_id)
            self.broadcast(
                {
                    "topic": "acq/progress",
                    "payload": {
                        "status": "completed" if result.status == StackStatus.COMPLETED else "failed",
                        "stack_id": stack_id,
                        "error": result.error_message,
                    },
                },
                with_status=True,
            )
        except Exception as e:
            log.exception("Acquisition failed for %s", stack_id)
            self.broadcast(
                {"topic": "acq/progress", "payload": {"status": "failed", "stack_id": stack_id, "error": str(e)}},
                with_status=True,
            )

    async def _run_all(self) -> None:
        stacks = self.session.stacks
        pending = [s for s in stacks if s.status == StackStatus.PLANNED]
        total = len(pending)

        self.broadcast(
            {"topic": "acq/progress", "payload": {"status": "started", "total": total, "completed": 0}},
            with_status=True,
        )

        completed = 0
        for stack in pending:
            try:
                result = await self.session.acquire_stack(stack.stack_id)
                if result.status == StackStatus.COMPLETED:
                    completed += 1
                self.broadcast(
                    {
                        "topic": "acq/progress",
                        "payload": {
                            "status": "in_progress",
                            "stack_id": stack.stack_id,
                            "total": total,
                            "completed": completed,
                        },
                    },
                    with_status=True,
                )
            except Exception as e:
                log.exception("Acquisition failed for %s", stack.stack_id)
                self.broadcast(
                    {
                        "topic": "acq/progress",
                        "payload": {"status": "failed", "stack_id": stack.stack_id, "error": str(e)},
                    },
                    with_status=True,
                )

        self.broadcast(
            {"topic": "acq/progress", "payload": {"status": "completed", "total": total, "completed": completed}},
            with_status=True,
        )


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
