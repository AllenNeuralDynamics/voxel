import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from vxl.stack import StackStatus
from vxlib import fire_and_forget

from ._deps import SessionDep

log = logging.getLogger(__name__)
router = APIRouter(prefix="/acquisition", tags=["acquisition"])


@router.post("/start")
async def start_acquisition(svc: SessionDep) -> dict[str, Any]:
    """Start acquisition for all PLANNED stacks."""
    pending = [s for s in svc.session.stacks if s.status == StackStatus.PLANNED]
    if not pending:
        raise HTTPException(status_code=400, detail="No planned stacks to acquire")
    fire_and_forget(svc.session.acquire_all(), log=log)
    return {"status": "started", "pending": len(pending)}


@router.post("/start/{stack_id}")
async def start_stack_acquisition(stack_id: str, svc: SessionDep) -> dict[str, Any]:
    if stack_id not in svc.session.stacks:
        raise HTTPException(status_code=404, detail=f"Stack {stack_id} not found")
    stack = svc.session.stacks[stack_id]
    if stack.status != StackStatus.PLANNED:
        raise HTTPException(
            status_code=400,
            detail=f"Stack {stack_id} has status {stack.status}, expected planned",
        )
    fire_and_forget(svc.session.acquire_stack(stack_id), log=log)
    return {"status": "started", "stack_id": stack_id}


@router.post("/stop")
async def stop_acquisition() -> dict[str, str]:
    """Stop the current acquisition (best-effort — not always supported by the engine)."""
    log.warning("Acquisition stop requested — not currently supported by the engine")
    return {"status": "stop-requested"}
