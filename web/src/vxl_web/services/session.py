"""Session-level service for Voxel acquisition control.

This service owns the Session and RigService, handling:
- Session state management
- Acquisition control
- Session info/status/metadata endpoints

Plan, workflow, and rig endpoints are in their own modules.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from vxl import AcquisitionPlan, RigMode, Session
from vxl.camera.preview import PreviewConfig
from vxl.metadata import discover_metadata_targets, resolve_metadata_class
from vxl.session import GridConfig, WorkflowStepConfig
from vxl.tile import Stack, StackStatus, Tile
from vxlib import fire_and_forget

from .rig import BroadcastCallback, RigService

info_router = APIRouter(prefix="/session", tags=["session"])
log = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    """Return an ISO 8601 timestamp in UTC."""
    return datetime.now(UTC).isoformat()


class SessionInfo(BaseModel):
    """Static session information fetched once at session start."""

    session_dir: str
    session_name: str
    metadata_target: str
    metadata_schema: dict[str, Any]
    workflow_steps: list[WorkflowStepConfig]
    rig_name: str


class SessionStatus(BaseModel):
    """Dynamic session state broadcast via WebSocket."""

    # Rig status
    active_profile_id: str | None
    mode: RigMode
    preview: dict[str, PreviewConfig] = Field(default_factory=dict)

    # Session status
    metadata: dict[str, Any]
    grid_locked: bool
    workflow_committed: str | None

    # Acquisition plan (per-profile grid configs + all stacks)
    plan: AcquisitionPlan

    # Convenience fields (active profile's data)
    grid_config: GridConfig | None
    tiles: list[Tile]
    stacks: list[Stack]

    # Derived values
    fov_um: tuple[float, float] | None = None

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

        # Subscribe to FOV changes to trigger status broadcasts
        self._unsubscribe_fov = session.rig.subscribe("fov", self._on_fov_changed)

        # Compose RigService with broadcast callback
        self.rig_service = RigService(
            rig=session.rig,
            broadcast=broadcast,
        )

    async def _on_fov_changed(self, _fov: tuple[float, float]) -> None:
        """Broadcast updated status when FOV changes."""
        self.broadcast({}, with_status=True)

    # ==================== Info & Status ====================

    def get_info(self) -> SessionInfo:
        """Get static session information (fetched once at session start)."""
        cls = resolve_metadata_class(self.session.metadata_target)
        schema = cls.model_json_schema()

        return SessionInfo(
            session_dir=str(self.session.session_dir),
            session_name=self.session.session_name,
            metadata_target=self.session.metadata_target,
            metadata_schema=schema,
            workflow_steps=self.session.workflow_steps,
            rig_name=self.session.rig.config.info.name,
        )

    async def get_status(self) -> SessionStatus:
        """Get current dynamic session status."""
        tiles = await self.session.get_tiles()
        preview = await self.session.rig.get_channel_preview_configs()

        try:
            fov_um = self.session.get_fov_size()
        except ValueError:
            fov_um = None

        return SessionStatus(
            active_profile_id=self.session.rig.active_profile_id,
            mode=self.session.rig.mode,
            metadata=self.session.metadata,
            grid_locked=self.session.grid_locked,
            workflow_committed=self.session.workflow_committed,
            plan=self.session.plan,
            grid_config=self.session.grid_config,
            tiles=tiles,
            stacks=self.session.stacks,
            fov_um=fov_um,
            preview=preview,
            timestamp=_utc_timestamp(),
        )

    # ==================== Message Handling ====================

    async def handle_message(self, client_id: str, topic: str, payload: dict[str, Any]) -> None:
        """Handle incoming message from a client.

        Only handles rig-level WS topics (preview/*, device/*, profile/update)
        and acquisition topics (acq/start, acq/stop).
        Plan, workflow, and profile-prop topics are now REST-only.
        """
        # Try rig service first (preview/*, device/*, profile/update)
        if await self.rig_service.handle_message(client_id, topic, payload):
            return

        # Handle acquisition topics
        match topic:
            case "acq/start":
                await self.handle_acq_start(payload)
            case "acq/stop":
                await self.handle_acq_stop()
            case _:
                log.warning("Unknown topic from client %s: %s", client_id, topic)

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


# ==================== Dependencies ====================


def get_session_service(request: Request) -> SessionService:
    """Dependency helper for HTTP routes requiring an active session."""
    app_service = request.app.state.app_service
    if app_service.session_service is None:
        raise HTTPException(status_code=503, detail="No active session")
    return app_service.session_service


# ==================== REST Endpoints ====================


class MetadataUpdateRequest(BaseModel):
    """Request model for updating session metadata."""

    metadata: dict[str, Any]


class AcquireRequest(BaseModel):
    """Request model for starting acquisition."""

    tile_id: str | None = Field(default=None, description="Specific tile to acquire, or None for all pending")


@info_router.get("/info")
async def get_session_info(service: Annotated[SessionService, Depends(get_session_service)]) -> SessionInfo:
    """Get static session information (fetched once at session start)."""
    return service.get_info()


@info_router.patch("/metadata")
async def update_metadata(
    request: MetadataUpdateRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, Any]:
    """Update session metadata (annotation fields always, provenance fields only pre-acquisition)."""
    try:
        service.session.update_metadata(request.metadata)
        service.broadcast({}, with_status=True)
        return {"metadata": service.session.metadata}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class MetadataTargetRequest(BaseModel):
    """Request model for changing the metadata schema class."""

    target: str


@info_router.patch("/metadata-target")
async def update_metadata_target(
    request: MetadataTargetRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> SessionInfo:
    """Change the metadata schema class. Resets metadata to new schema defaults."""
    try:
        service.session.set_metadata_target(request.target)
        service.broadcast({}, with_status=True)
        return service.get_info()
    except (ValueError, TypeError, ImportError, AttributeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@info_router.get("/metadata-targets")
async def get_metadata_targets() -> dict[str, Any]:
    """Return available metadata targets for the session metadata schema selector."""
    return {"targets": discover_metadata_targets()}
