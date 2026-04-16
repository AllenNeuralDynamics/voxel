"""Session service — composes peer services, owns WS router, handles session/grid/output REST.

Peer services (profiles, preview, devices, stacks, acquisition) are constructed
here and exposed as attributes. Inbound WS messages flow through ``handle_message``
which delegates via ``WsRouter``.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from vxl import Session
from vxl.camera.preview import PreviewConfig
from vxl.config import GridConfig
from vxl.metadata import resolve_metadata_class
from vxl.session import SessionMode

from .acquisition import AcquisitionService
from .devices import DevicesService, DevicesSnapshot, snapshot_devices
from .preview import PreviewService
from .profiles import ProfilesService
from .stacks import StacksService
from .ws import BroadcastCallback, WsRouter

log = logging.getLogger(__name__)
info_router = APIRouter(tags=["session"])


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


# ==================== Serialization models ====================


class SessionDetails(BaseModel):
    config: dict[str, Any]
    metadata_schema: dict[str, Any]
    devices: DevicesSnapshot


class SessionStateUpdate(BaseModel):
    active_profile_id: str | None
    mode: SessionMode
    preview: dict[str, PreviewConfig] = {}
    metadata: dict[str, Any]
    plan: dict[str, Any]
    output: dict[str, Any]
    grid: dict[str, Any]
    stacks: dict[str, Any]
    stack_order: list[str]
    fov: tuple[float, float] | None = None
    timestamp: str


# ==================== Service ====================


class SessionService:
    """Composition root for per-service REST + WS. Owns the inbound WS router."""

    def __init__(self, session: Session, broadcast: BroadcastCallback) -> None:
        self.session = session
        self.broadcast = broadcast

        # Compose peers
        self.profiles = ProfilesService(session, broadcast)
        self.preview = PreviewService(session, broadcast)
        self.devices = DevicesService(session, broadcast)
        self.stacks = StacksService(session, broadcast)
        self.acquisition = AcquisitionService(session, broadcast)

        # WS router — delegates by topic prefix
        self._router = WsRouter([self.profiles, self.preview, self.devices, self.stacks, self.acquisition])

        # Subscribe to FOV changes for status broadcasts
        self._unsub_fov = session.rig.profiles.fov_changed.subscribe(self._on_fov_changed)

    async def open(self) -> None:
        """Finish async setup — must be awaited after construction.

        Sub-services with async subscriptions (currently just ``devices``)
        complete them here.
        """
        await self.devices.open()

    async def close(self) -> None:
        """Tear down all peer services in reverse construction order. No broadcasts.

        Each sub-service is closed independently; one failure doesn't block siblings.
        Call this before backend session teardown (VoxelApp.close_session) so the
        rig is still alive while subscriptions are unwired.
        """
        self._unsub_fov()
        for close in (
            self.acquisition.close,
            self.stacks.close,
            self.devices.close,
            self.preview.close,
            self.profiles.close,
        ):
            try:
                await close()
            except Exception:
                log.exception("Error in %s", close.__qualname__)

    async def stop_preview_for_idle(self) -> None:
        """Stop preview when the last WS client disconnects (bleaching safety). No broadcast."""
        await self.preview.close()

    # ---- WS ----

    async def handle_message(self, sender_id: str, topic: str, payload: dict[str, Any]) -> None:
        try:
            await self._router.dispatch(sender_id, topic, payload)
        except Exception as e:
            log.exception("Error handling WS message %s", topic)
            self.broadcast({"topic": "error", "payload": {"error": str(e), "topic": topic}})

    # ---- Status ----

    async def get_session_details(self) -> SessionDetails:
        cls = resolve_metadata_class(self.session.metadata_schema)
        return SessionDetails(
            config=self.session.config.model_dump(mode="json"),
            metadata_schema=cls.model_json_schema(),
            devices=await snapshot_devices(self.session),
        )

    async def get_status(self) -> SessionStateUpdate:
        preview_configs = await self.preview.session.preview.get_channel_preview_configs()
        profiles = self.session.rig.profiles
        return SessionStateUpdate(
            active_profile_id=profiles.active_id,
            mode=self.session.mode,
            preview=preview_configs,
            metadata=self.session.metadata,
            plan=self.session.config.plan.model_dump(mode="json"),
            output=self.session.config.output.model_dump(mode="json"),
            grid=self.session.config.grid.model_dump(mode="json"),
            stacks={s.stack_id: s.model_dump() for s in self.session.stacks},
            stack_order=self.session.stacks.compute_order(),
            fov=profiles.fov,
            timestamp=_utc_timestamp(),
        )

    # ---- Private ----

    async def _on_fov_changed(self, _fov: tuple[float, float]) -> None:
        self.broadcast({}, with_status=True)


# ==================== Dependency ====================


def get_session_service(request: Request) -> SessionService:
    app_service = request.app.state.app_service
    if app_service.session_service is None:
        raise HTTPException(status_code=503, detail="No active session")
    return app_service.session_service


# ==================== Request models ====================


class MetadataUpdateRequest(BaseModel):
    metadata: dict[str, Any]


class MetadataSchemaRequest(BaseModel):
    """Wire field ``schema`` maps to Python ``target`` — avoids collision with ``BaseModel.schema``."""

    model_config = ConfigDict(populate_by_name=True)
    target: str = Field(alias="schema", serialization_alias="schema")


class GridUpdateRequest(BaseModel):
    x_offset: float | None = None
    y_offset: float | None = None
    overlap_x: float | None = None
    overlap_y: float | None = None


class OutputUpdateRequest(BaseModel):
    store_path: str | None = None
    max_level: str | None = None
    compression: str | None = None


# ==================== Session REST ====================


@info_router.get("/session/details")
async def get_session_details(
    service: Annotated[SessionService, Depends(get_session_service)],
) -> SessionDetails:
    return await service.get_session_details()


@info_router.patch("/session/metadata")
async def update_metadata(
    request: MetadataUpdateRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, Any]:
    try:
        service.session.update_metadata(request.metadata)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    service.broadcast({}, with_status=True)
    return {"metadata": service.session.metadata}


@info_router.patch("/session/metadata-schema")
async def update_metadata_schema(
    request: MetadataSchemaRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> SessionDetails:
    try:
        service.session.set_metadata_schema(request.target)
    except (ValueError, TypeError, ImportError, AttributeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    service.broadcast({}, with_status=True)
    return await service.get_session_details()


# ==================== Grid REST ====================


@info_router.get("/grid")
async def get_grid(service: Annotated[SessionService, Depends(get_session_service)]) -> GridConfig:
    return service.session.config.grid


@info_router.patch("/grid")
async def update_grid(
    request: GridUpdateRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> GridConfig:
    grid = service.session.config.grid
    try:
        if request.x_offset is not None:
            grid.x_offset = request.x_offset
        if request.y_offset is not None:
            grid.y_offset = request.y_offset
        if request.overlap_x is not None:
            grid.overlap_x = request.overlap_x
        if request.overlap_y is not None:
            grid.overlap_y = request.overlap_y
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    service.broadcast({}, with_status=True)
    return grid


# ==================== Output REST ====================


@info_router.get("/output")
async def get_output(service: Annotated[SessionService, Depends(get_session_service)]) -> dict[str, Any]:
    return service.session.config.output.model_dump(mode="json")


@info_router.patch("/output")
async def update_output(
    request: OutputUpdateRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, Any]:
    from pathlib import Path  # noqa: PLC0415 — conditional import kept local

    output = service.session.config.output
    if request.store_path is not None:
        output.store_path = Path(request.store_path)
    if request.max_level is not None:
        output.max_level = request.max_level  # type: ignore[assignment]
    if request.compression is not None:
        output.compression = request.compression  # type: ignore[assignment]
    service.broadcast({}, with_status=True)
    return output.model_dump(mode="json")
