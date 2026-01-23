"""Session-level service for Voxel acquisition control.

This service owns the Session and RigService, handling:
- Session state management (grid, stacks)
- Acquisition control

It receives a broadcast callback from AppService for client communication.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from voxel import RigMode, Session
from voxel.config import TileOrder
from voxel.session import GridConfig
from voxel.tile import Stack, StackStatus, Tile
from vxlib import fire_and_forget

from .rig import BroadcastCallback, RigService
from .rig import router as rig_router

session_router = APIRouter(tags=["session"])
session_router.include_router(rig_router)  # Include rig routes under session router
log = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    """Return an ISO 8601 timestamp in UTC."""
    return datetime.now(UTC).isoformat()


class SessionStatus(BaseModel):
    """Combined rig and session status with full tile/stack data."""

    # Rig status
    active_profile_id: str | None
    mode: RigMode

    # Session status
    session_dir: str
    grid_locked: bool

    # Full data (replaces separate broadcasts)
    grid_config: GridConfig
    tile_order: TileOrder
    tiles: list[Tile]
    stacks: list[Stack]

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
        self.broadcast = broadcast

        # Compose RigService with broadcast callback
        self.rig_service = RigService(
            rig=session.rig,
            broadcast=broadcast,
        )

    # ==================== Status ====================

    async def get_status(self) -> SessionStatus:
        """Get current session status with full tile/stack data."""
        tiles = await self.session.get_tiles()

        return SessionStatus(
            active_profile_id=self.session.rig.active_profile_id,
            mode=self.session.rig.mode,
            session_dir=str(self.session.session_dir),
            grid_locked=self.session.grid_locked,
            grid_config=self.session.grid_config,
            tile_order=self.session.tile_order,
            tiles=tiles,
            stacks=self.session.stacks,
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
            case "grid/set_tile_order":
                await self._handle_tile_order(payload)
            case "stacks/add":
                await self._handle_stacks_add(payload)
            case "stacks/edit":
                await self._handle_stacks_edit(payload)
            case "stacks/remove":
                await self._handle_stacks_remove(payload)
            case "acq/start":
                await self.handle_acq_start(payload)
            case "acq/stop":
                await self.handle_acq_stop()
            case _:
                log.warning("Unknown topic from client %s: %s", client_id, topic)

    # ==================== Grid Management ====================

    async def _handle_grid_offset(self, payload: dict[str, Any]) -> None:
        """Handle grid offset update."""
        x_offset = payload.get("x_offset_um")
        y_offset = payload.get("y_offset_um")

        if x_offset is None or y_offset is None:
            raise ValueError("Missing x_offset_um or y_offset_um")

        await self.session.set_grid_offset(x_offset, y_offset)
        # Status broadcast includes grid_config, tiles, and stacks
        self.broadcast({}, with_status=True)

    async def _handle_grid_overlap(self, payload: dict[str, Any]) -> None:
        """Handle grid overlap update."""
        overlap = payload.get("overlap")

        if overlap is None:
            raise ValueError("Missing overlap")

        await self.session.set_overlap(overlap)
        # Status broadcast includes grid_config, tiles, and stacks
        self.broadcast({}, with_status=True)

    async def _handle_tile_order(self, payload: dict[str, Any]) -> None:
        """Handle tile order update."""
        tile_order = payload.get("tile_order")

        if tile_order is None:
            raise ValueError("Missing tile_order")

        self.session.set_tile_order(tile_order)
        # Status broadcast includes tile_order and stacks (re-sorted)
        self.broadcast({}, with_status=True)

    # ==================== Stack Management ====================

    async def _handle_stacks_add(self, payload: dict[str, Any]) -> None:
        """Handle bulk stack add request.

        Payload: { "stacks": [{ row, col, z_start_um, z_end_um }, ...] }
        """
        stacks = payload.get("stacks")
        if not stacks or not isinstance(stacks, list):
            raise ValueError("Missing or invalid 'stacks' array")

        await self.session.add_stacks(stacks)
        self.broadcast({}, with_status=True)

    async def _handle_stacks_edit(self, payload: dict[str, Any]) -> None:
        """Handle bulk stack edit request.

        Payload: { "edits": [{ row, col, z_start_um?, z_end_um? }, ...] }
        """
        edits = payload.get("edits")
        if not edits or not isinstance(edits, list):
            raise ValueError("Missing or invalid 'edits' array")

        self.session.edit_stacks(edits)
        self.broadcast({}, with_status=True)

    async def _handle_stacks_remove(self, payload: dict[str, Any]) -> None:
        """Handle bulk stack remove request.

        Payload: { "positions": [{ row, col }, ...] }
        """
        positions = payload.get("positions")
        if not positions or not isinstance(positions, list):
            raise ValueError("Missing or invalid 'positions' array")

        self.session.remove_stacks(positions)
        self.broadcast({}, with_status=True)

    # ==================== Acquisition ====================

    async def handle_acq_start(self, payload: dict[str, Any]) -> None:
        """Handle acquisition start request."""
        tile_id = payload.get("tile_id")  # Optional - if None, acquire all

        if tile_id:
            # Acquire single stack
            fire_and_forget(self._run_single_acquisition(tile_id), log=log)
        else:
            # Acquire all pending stacks
            fire_and_forget(self._run_full_acquisition(), log=log)

    async def handle_acq_stop(self) -> None:
        """Handle acquisition stop request."""
        # TODO: Implement acquisition cancellation
        log.warning("Acquisition stop not yet implemented")

    async def _run_single_acquisition(self, tile_id: str) -> None:
        """Run acquisition for a single stack."""
        try:
            self.broadcast(
                {"topic": "acq/progress", "payload": {"status": "started", "tile_id": tile_id}},
                with_status=True,
            )
            result = await self.session.acquire_stack(tile_id)
            self.broadcast(
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
            log.exception(f"Acquisition failed for {tile_id}")
            self.broadcast(
                {"topic": "acq/progress", "payload": {"status": "failed", "tile_id": tile_id, "error": str(e)}},
                with_status=True,
            )
        # Status broadcast (with_status=True) already includes stacks

    async def _run_full_acquisition(self) -> None:
        """Run acquisition for all pending stacks."""
        pending = [s for s in self.session.stacks if s.status == StackStatus.PLANNED]
        total = len(pending)

        self.broadcast(
            {"topic": "acq/progress", "payload": {"status": "started", "total": total, "completed": 0}},
            with_status=True,
        )

        completed = 0
        for stack in pending:
            try:
                result = await self.session.acquire_stack(stack.tile_id)
                if result.status == StackStatus.COMPLETED:
                    completed += 1
                self.broadcast(
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
                log.exception(f"Acquisition failed for {stack.tile_id}")
                self.broadcast(
                    {
                        "topic": "acq/progress",
                        "payload": {"status": "failed", "tile_id": stack.tile_id, "error": str(e)},
                    },
                    with_status=True,
                )
            # Status broadcast (with_status=True) already includes stacks

        self.broadcast(
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
async def get_session_status(service: Annotated[SessionService, Depends(get_session_service)]) -> SessionStatus:
    """Get current session status."""
    return await service.get_status()


@session_router.get("/session/grid")
async def get_grid(service: Annotated[SessionService, Depends(get_session_service)]) -> GridConfig:
    """Get current grid configuration."""
    return service.session.grid_config


class GridUpdateRequest(BaseModel):
    """Request model for updating grid configuration."""

    x_offset_um: float | None = None
    y_offset_um: float | None = None
    overlap: float | None = None


@session_router.patch("/session/grid")
async def update_grid(
    request: GridUpdateRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> GridConfig:
    """Update grid configuration."""
    try:
        if request.x_offset_um is not None and request.y_offset_um is not None:
            await service.session.set_grid_offset(request.x_offset_um, request.y_offset_um)
        if request.overlap is not None:
            await service.session.set_overlap(request.overlap)

        # Status broadcast includes grid_config, tiles, and stacks
        service.broadcast({}, with_status=True)
        return service.session.grid_config
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e  # Conflict - grid locked
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class TileOrderRequest(BaseModel):
    """Request model for setting tile order."""

    tile_order: TileOrder


@session_router.put("/session/tile-order")
async def set_tile_order(
    request: TileOrderRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, TileOrder]:
    """Set tile acquisition order."""
    service.session.set_tile_order(request.tile_order)
    service.broadcast({}, with_status=True)
    return {"tile_order": service.session.tile_order}


@session_router.get("/session/stacks")
async def list_stacks(service: Annotated[SessionService, Depends(get_session_service)]) -> dict:
    """Get all stacks."""
    return {
        "stacks": [s.model_dump() for s in service.session.stacks],
        "count": len(service.session.stacks),
    }


class StackInput(BaseModel):
    """Input model for a single stack."""

    row: int
    col: int
    z_start_um: float
    z_end_um: float


class AddStacksRequest(BaseModel):
    """Request model for adding stacks (bulk)."""

    stacks: list[StackInput]


@session_router.post("/session/stacks")
async def add_stacks(
    request: AddStacksRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Add stacks at the specified grid positions (bulk)."""
    try:
        stacks = await service.session.add_stacks([s.model_dump() for s in request.stacks])
        service.broadcast({}, with_status=True)
        return {"added": len(stacks), "stacks": [s.model_dump() for s in stacks]}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class StackEditInput(BaseModel):
    """Input model for editing a single stack."""

    row: int
    col: int
    z_start_um: float | None = None
    z_end_um: float | None = None


class EditStacksRequest(BaseModel):
    """Request model for editing stacks (bulk)."""

    edits: list[StackEditInput]


@session_router.patch("/session/stacks")
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


class StackPosition(BaseModel):
    """Position identifier for a stack."""

    row: int
    col: int


class RemoveStacksRequest(BaseModel):
    """Request model for removing stacks (bulk)."""

    positions: list[StackPosition]


@session_router.delete("/session/stacks")
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


class AcquireRequest(BaseModel):
    """Request model for starting acquisition."""

    tile_id: str | None = Field(default=None, description="Specific tile to acquire, or None for all pending")


@session_router.post("/session/acquire")
async def start_acquisition(
    request: AcquireRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Start acquisition."""
    if service.session.rig.mode == RigMode.ACQUIRING:
        raise HTTPException(status_code=409, detail="Acquisition already in progress")

    await service.handle_acq_start({"tile_id": request.tile_id})
    return {"status": "started", "tile_id": request.tile_id}


@session_router.post("/session/acquire/stop")
async def stop_acquisition(service: Annotated[SessionService, Depends(get_session_service)]) -> dict:
    """Stop acquisition."""
    await service.handle_acq_stop()
    return {"status": "stopping"}
