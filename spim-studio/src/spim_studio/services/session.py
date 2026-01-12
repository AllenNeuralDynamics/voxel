"""Session-level service for SPIM acquisition control.

This service owns the Session and RigService, handling:
- Session state management (grid, stacks)
- Acquisition control

It receives a broadcast callback from AppService for client communication.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from spim_rig import RigMode, Session
from spim_rig.session import GridConfig
from spim_rig.tile import Stack, StackStatus

from .rig import BroadcastCallback, RigService
from .rig import router as rig_router

session_router = APIRouter(tags=["session"])
session_router.include_router(rig_router)  # Include rig routes under session router
log = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    """Return an ISO 8601 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


class SessionStatus(BaseModel):
    """Combined rig and session status."""

    # Rig status
    active_profile_id: str | None
    mode: RigMode

    # Session status
    session_dir: str
    grid_locked: bool
    stack_count: int
    pending_count: int
    completed_count: int

    timestamp: str


class SessionService:
    """Session-level service owning Session and RigService.

    Receives a broadcast callback from AppService for client communication.
    """

    def __init__(
        self,
        session: Session,
        broadcast: BroadcastCallback,
    ):
        self.session = session
        self._broadcast = broadcast

        # Compose RigService with broadcast callback
        self.rig_service = RigService(
            rig=session.rig,
            broadcast=broadcast,
        )

    # ==================== Status ====================

    def get_status(self) -> SessionStatus:
        """Get current session status."""
        stacks = self.session.stacks
        pending = sum(1 for s in stacks if s.status == StackStatus.PLANNED)
        completed = sum(1 for s in stacks if s.status == StackStatus.COMPLETED)

        return SessionStatus(
            active_profile_id=self.session.rig.active_profile_id,
            mode=self.session.rig.mode,
            session_dir=str(self.session.session_dir),
            grid_locked=self.session.grid_locked,
            stack_count=len(stacks),
            pending_count=pending,
            completed_count=completed,
            timestamp=_utc_timestamp(),
        )

    # ==================== Message Handling ====================

    async def handle_message(self, client_id: str, topic: str, payload: dict[str, Any]) -> None:
        """Handle incoming message from a client.

        Args:
            client_id: The client ID (for error context).
            topic: The message topic.
            payload: The message payload.
        """
        # Try rig service first
        if await self.rig_service.handle_message(topic, payload):
            return

        # Handle session-level topics
        match topic:
            case "grid/set_offset":
                await self._handle_grid_offset(payload)
            case "grid/set_overlap":
                await self._handle_grid_overlap(payload)
            case "stack/add":
                await self._handle_stack_add(payload)
            case "stack/edit":
                await self._handle_stack_edit(payload)
            case "stack/remove":
                await self._handle_stack_remove(payload)
            case "acq/start":
                await self._handle_acq_start(payload)
            case "acq/stop":
                await self._handle_acq_stop()
            case _:
                log.warning("Unknown topic from client %s: %s", client_id, topic)

    # ==================== Grid Management ====================

    async def _handle_grid_offset(self, payload: dict[str, Any]) -> None:
        """Handle grid offset update."""
        x_offset = payload.get("x_offset_um")
        y_offset = payload.get("y_offset_um")

        if x_offset is None or y_offset is None:
            raise ValueError("Missing x_offset_um or y_offset_um")

        self.session.set_grid_offset(x_offset, y_offset)
        self._broadcast({"topic": "grid/updated", "payload": self.session.grid_config.model_dump()}, with_status=True)

    async def _handle_grid_overlap(self, payload: dict[str, Any]) -> None:
        """Handle grid overlap update."""
        overlap = payload.get("overlap")

        if overlap is None:
            raise ValueError("Missing overlap")

        self.session.set_overlap(overlap)
        self._broadcast({"topic": "grid/updated", "payload": self.session.grid_config.model_dump()}, with_status=True)

    # ==================== Stack Management ====================

    async def _handle_stack_add(self, payload: dict[str, Any]) -> None:
        """Handle stack add request."""
        row = payload.get("row")
        col = payload.get("col")
        z_start = payload.get("z_start_um")
        z_end = payload.get("z_end_um")
        z_step = payload.get("z_step_um")

        if row is None or col is None or z_start is None or z_end is None or z_step is None:
            raise ValueError("Missing required fields: row, col, z_start_um, z_end_um, z_step_um")

        await self.session.add_stack(int(row), int(col), float(z_start), float(z_end), float(z_step))
        self._broadcast_stacks(with_status=True)

    async def _handle_stack_edit(self, payload: dict[str, Any]) -> None:
        """Handle stack edit request."""
        tile_id = payload.get("tile_id")
        if not tile_id:
            raise ValueError("Missing tile_id")

        self.session.edit_stack(
            tile_id,
            z_start_um=payload.get("z_start_um"),
            z_end_um=payload.get("z_end_um"),
            z_step_um=payload.get("z_step_um"),
        )
        self._broadcast_stacks()

    async def _handle_stack_remove(self, payload: dict[str, Any]) -> None:
        """Handle stack remove request."""
        tile_id = payload.get("tile_id")
        if not tile_id:
            raise ValueError("Missing tile_id")

        self.session.remove_stack(tile_id)
        self._broadcast_stacks(with_status=True)

    def _broadcast_stacks(self, with_status: bool = False) -> None:
        """Broadcast stack list to all clients."""
        stacks = [s.model_dump() for s in self.session.stacks]
        self._broadcast({"topic": "stacks/updated", "payload": {"stacks": stacks}}, with_status=with_status)

    # ==================== Acquisition ====================

    async def _handle_acq_start(self, payload: dict[str, Any]) -> None:
        """Handle acquisition start request."""
        tile_id = payload.get("tile_id")  # Optional - if None, acquire all

        if tile_id:
            # Acquire single stack
            asyncio.create_task(self._run_single_acquisition(tile_id))
        else:
            # Acquire all pending stacks
            asyncio.create_task(self._run_full_acquisition())

    async def _handle_acq_stop(self) -> None:
        """Handle acquisition stop request."""
        # TODO: Implement acquisition cancellation
        log.warning("Acquisition stop not yet implemented")

    async def _run_single_acquisition(self, tile_id: str) -> None:
        """Run acquisition for a single stack."""
        try:
            self._broadcast(
                {"topic": "acq/progress", "payload": {"status": "started", "tile_id": tile_id}}, with_status=True
            )
            result = await self.session.acquire_stack(tile_id)
            self._broadcast(
                {
                    "topic": "acq/progress",
                    "payload": {
                        "status": "completed" if result.status == StackStatus.COMPLETED else "failed",
                        "tile_id": tile_id,
                        "error": result.error_message,
                    },
                },
                with_status=True,
            )
        except Exception as e:
            log.error(f"Acquisition failed for {tile_id}: {e}", exc_info=True)
            self._broadcast(
                {"topic": "acq/progress", "payload": {"status": "failed", "tile_id": tile_id, "error": str(e)}},
                with_status=True,
            )
        finally:
            self._broadcast_stacks()

    async def _run_full_acquisition(self) -> None:
        """Run acquisition for all pending stacks."""
        pending = [s for s in self.session.stacks if s.status == StackStatus.PLANNED]
        total = len(pending)

        self._broadcast(
            {"topic": "acq/progress", "payload": {"status": "started", "total": total, "completed": 0}},
            with_status=True,
        )

        completed = 0
        for stack in pending:
            try:
                result = await self.session.acquire_stack(stack.tile_id)
                if result.status == StackStatus.COMPLETED:
                    completed += 1
                self._broadcast(
                    {
                        "topic": "acq/progress",
                        "payload": {
                            "status": "in_progress",
                            "tile_id": stack.tile_id,
                            "total": total,
                            "completed": completed,
                        },
                    },
                    with_status=True,
                )
            except Exception as e:
                log.error(f"Acquisition failed for {stack.tile_id}: {e}", exc_info=True)
                self._broadcast(
                    {
                        "topic": "acq/progress",
                        "payload": {"status": "failed", "tile_id": stack.tile_id, "error": str(e)},
                    },
                    with_status=True,
                )

            self._broadcast_stacks()

        self._broadcast(
            {"topic": "acq/progress", "payload": {"status": "completed", "total": total, "completed": completed}},
            with_status=True,
        )


# ==================== REST Endpoints ====================
# Note: These require an active session. AppService guards access.


def get_session_service(request: Request) -> SessionService:
    """Dependency helper for HTTP routes."""
    app_service = request.app.state.app_service
    if app_service.session_service is None:
        raise HTTPException(status_code=503, detail="No active session")
    return app_service.session_service


@session_router.get("/session/status")
async def get_session_status(service: SessionService = Depends(get_session_service)) -> SessionStatus:
    """Get current session status."""
    return service.get_status()


@session_router.get("/session/grid")
async def get_grid(service: SessionService = Depends(get_session_service)) -> GridConfig:
    """Get current grid configuration."""
    return service.session.grid_config


class GridUpdateRequest(BaseModel):
    """Request model for updating grid configuration."""

    x_offset_um: float | None = None
    y_offset_um: float | None = None
    overlap: float | None = None


@session_router.patch("/session/grid")
async def update_grid(request: GridUpdateRequest, service: SessionService = Depends(get_session_service)) -> GridConfig:
    """Update grid configuration."""
    try:
        if request.x_offset_um is not None and request.y_offset_um is not None:
            service.session.set_grid_offset(request.x_offset_um, request.y_offset_um)
        if request.overlap is not None:
            service.session.set_overlap(request.overlap)

        service._broadcast({"topic": "grid/updated", "payload": service.session.grid_config.model_dump()})
        return service.session.grid_config
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))  # Conflict - grid locked
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@session_router.get("/session/stacks")
async def list_stacks(service: SessionService = Depends(get_session_service)) -> dict:
    """Get all stacks."""
    return {
        "stacks": [s.model_dump() for s in service.session.stacks],
        "count": len(service.session.stacks),
    }


class AddStackRequest(BaseModel):
    """Request model for adding a stack."""

    row: int
    col: int
    z_start_um: float
    z_end_um: float
    z_step_um: float


@session_router.post("/session/stacks")
async def add_stack(request: AddStackRequest, service: SessionService = Depends(get_session_service)) -> Stack:
    """Add a stack at the specified grid position."""
    try:
        stack = await service.session.add_stack(
            row=request.row,
            col=request.col,
            z_start_um=request.z_start_um,
            z_end_um=request.z_end_um,
            z_step_um=request.z_step_um,
        )
        service._broadcast_stacks()
        return stack
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class EditStackRequest(BaseModel):
    """Request model for editing a stack."""

    z_start_um: float | None = None
    z_end_um: float | None = None
    z_step_um: float | None = None


@session_router.patch("/session/stacks/{tile_id}")
async def edit_stack(
    tile_id: str,
    request: EditStackRequest,
    service: SessionService = Depends(get_session_service),
) -> Stack:
    """Edit a stack's z parameters."""
    try:
        stack = service.session.edit_stack(
            tile_id,
            z_start_um=request.z_start_um,
            z_end_um=request.z_end_um,
            z_step_um=request.z_step_um,
        )
        service._broadcast_stacks()
        return stack
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@session_router.delete("/session/stacks/{tile_id}")
async def remove_stack(tile_id: str, service: SessionService = Depends(get_session_service)) -> dict:
    """Remove a stack."""
    try:
        service.session.remove_stack(tile_id)
        service._broadcast_stacks()
        return {"removed": tile_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class AcquireRequest(BaseModel):
    """Request model for starting acquisition."""

    tile_id: str | None = Field(default=None, description="Specific tile to acquire, or None for all pending")


@session_router.post("/session/acquire")
async def start_acquisition(
    request: AcquireRequest = AcquireRequest(), service: SessionService = Depends(get_session_service)
) -> dict:
    """Start acquisition."""
    if service.session.rig.mode == RigMode.ACQUIRING:
        raise HTTPException(status_code=409, detail="Acquisition already in progress")

    await service._handle_acq_start({"tile_id": request.tile_id})
    return {"status": "started", "tile_id": request.tile_id}


@session_router.post("/session/acquire/stop")
async def stop_acquisition(service: SessionService = Depends(get_session_service)) -> dict:
    """Stop acquisition."""
    await service._handle_acq_stop()
    return {"status": "stopping"}
