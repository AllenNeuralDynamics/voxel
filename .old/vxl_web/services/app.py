"""App-level service for Voxel.

Manages WebSocket client communication, log streaming from app startup,
session lifecycle (create/resume/fork/close) via VoxelApp, and app-level
status broadcasting. Mounts per-service routers.
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from vxl.app import VoxelApp
from vxl.metadata import discover_metadata_schema, resolve_metadata_class
from vxl.store import SessionListing, TemplateInfo
from vxl.system import DataRoot
from vxlib import ColormapGroup, fire_and_forget, get_colormap_catalog

from .acquisition import router as acquisition_router
from .devices import router as devices_router
from .profiles import router as profiles_router
from .session import SessionService, SessionStateUpdate, info_router
from .stacks import router as stacks_router
from .ws import MsgQueue

router = APIRouter(tags=["app"])
router.include_router(info_router)
router.include_router(profiles_router)
router.include_router(devices_router)
router.include_router(stacks_router)
router.include_router(acquisition_router)

log = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


AppStatus = Literal["idle", "launching", "ready"]


# ==================== Models ====================


class AppStatusUpdate(BaseModel):
    status: AppStatus
    session: SessionStateUpdate | None = None
    timestamp: str


class LogMessage(BaseModel):
    level: str
    message: str
    logger: str
    timestamp: str


class CreateSessionRequest(BaseModel):
    template: str | None = None
    source_session: str | None = None
    resume: str | None = None
    data_root: str | None = None
    name: str = ""
    description: str = ""
    collection: str = ""
    clear_stacks: bool = False


# ==================== Service ====================


class AppService:
    """App-level service managing WebSocket clients and session lifecycle."""

    def __init__(self, voxel_app: VoxelApp) -> None:
        self.voxel_app = voxel_app
        self.session_service: SessionService | None = None
        self.clients: dict[str, MsgQueue] = {}
        self._log_handler: _WebSocketLogHandler | None = None
        self._status: AppStatus = "idle"
        self._status_lock = asyncio.Lock()

        self._setup_log_capture()

    def _setup_log_capture(self) -> None:
        def _broadcast_log(record: logging.LogRecord) -> None:
            log_msg = LogMessage(
                level=record.levelname.lower(),
                message=record.getMessage(),
                logger=record.name,
                timestamp=_utc_timestamp(),
            )
            self._broadcast({"topic": "log/message", "payload": log_msg.model_dump()})

        self._log_handler = _WebSocketLogHandler(_broadcast_log)
        self._log_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(self._log_handler)

    def teardown_log_capture(self) -> None:
        if self._log_handler:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None

    # ==================== Client Management ====================

    def _broadcast(self, data: dict[str, Any] | bytes, with_status: bool = False, exclude: str | None = None) -> None:
        # No clients → nothing to do (prevents status-broadcast storms during shutdown,
        # which would otherwise query a closing rig and hang on ZMQ).
        if not self.clients:
            return

        if data:
            msg_type = "bytes" if isinstance(data, bytes) else "json"
            priority = 1 if msg_type == "bytes" else 0
            for client_id, queue in self.clients.items():
                if client_id == exclude:
                    continue
                queue.put(msg_type, data, priority=priority)

        if with_status:
            fire_and_forget(self._broadcast_status(), log=log, timeout=5.0)

    def _send_to_client(self, client_id: str, data: dict[str, Any]) -> None:
        queue = self.clients.get(client_id)
        if queue:
            queue.put("json", data)

    async def add_client(self, client_id: str, queue: MsgQueue) -> None:
        self.clients[client_id] = queue
        log.info("Client %s connected. Total: %d", client_id, len(self.clients))
        async with self._status_lock:
            status = await self.get_app_status()
            self._send_to_client(
                client_id,
                {"topic": "status", "payload": status.model_dump(mode="json")},
            )

    def remove_client(self, client_id: str) -> None:
        self.clients.pop(client_id, None)
        log.info("Client %s disconnected. Total: %d", client_id, len(self.clients))

    # ==================== Status ====================

    async def get_app_status(self) -> AppStatusUpdate:
        session_state = None
        if self.session_service:
            session_state = await self.session_service.get_status()

        return AppStatusUpdate(
            status=self._status,
            session=session_state,
            timestamp=_utc_timestamp(),
        )

    async def _broadcast_status(self) -> None:
        async with self._status_lock:
            try:
                status = await self.get_app_status()
                self._broadcast({"topic": "status", "payload": status.model_dump(mode="json")})
            except Exception as e:
                log.warning("Failed to broadcast status: %s", e)

    # ==================== Session Lifecycle ====================

    async def create_session(self, request: CreateSessionRequest) -> None:
        if self.session_service is not None:
            raise RuntimeError("A session is already active. Close it first.")
        if self._status == "launching":
            raise RuntimeError("A session is already being launched.")

        if request.resume:
            self.voxel_app.catalog.get_session_store(request.resume)
        elif request.template:
            pass  # catalog.fork() validates on call
        elif request.source_session:
            self.voxel_app.catalog.get_session_store(request.source_session)
        else:
            raise ValueError("One of 'template', 'source_session', or 'resume' must be provided")

        self._status = "launching"
        self._broadcast({}, with_status=True)

        async def _launch_session() -> None:
            try:
                if request.resume:
                    session = await self.voxel_app.resume_session(request.resume)
                else:
                    session = await self.voxel_app.create_session(
                        template=request.template,
                        source_session=request.source_session,
                        data_root_name=request.data_root,
                        name=request.name,
                        description=request.description,
                        collection=request.collection,
                        clear_stacks=request.clear_stacks,
                    )

                self.session_service = SessionService(session=session, broadcast=self._broadcast)
                await self.session_service.open()
                self._status = "ready"
                await self._broadcast_status()
            except Exception as e:
                log.exception("Failed to launch session")
                self.session_service = None
                self._status = "idle"
                self._broadcast(
                    {"topic": "error", "payload": {"error": str(e), "topic": "session/launch"}},
                    with_status=True,
                )

        fire_and_forget(_launch_session(), log=log)

    async def close_session(self) -> None:
        """Close the active session. One-way: never broadcasts from close paths.

        Order:
          1. Snapshot + null session_service; flip status to "idle".
          2. Broadcast idle status — session is still queryable but we ignore it.
          3. Tear down sub-services (no broadcasts — they short-circuit on empty clients).
          4. Close backend session + rig (this is where the cluster shutdown runs).
        """
        if self.session_service is None:
            raise RuntimeError("No active session to close")

        session_service = self.session_service
        self.session_service = None
        self._status = "idle"

        # Tell clients we're idle BEFORE destroying state. get_status() won't hit
        # the closing rig because session_service is already None on self.
        if self.clients:
            await self._broadcast_status()

        # Tear down in reverse construction order. Each step logs its own errors
        # and keeps the chain moving.
        try:
            await session_service.close()
        except Exception:
            log.exception("Error closing session service")
        try:
            await self.voxel_app.close_session()
        except Exception:
            log.exception("Error closing voxel app session")

    # ==================== WS message handling ====================

    async def handle_client_message(self, client_id: str, message: dict[str, Any]) -> None:
        topic = message.get("topic")
        payload = message.get("payload", {})

        if not topic:
            return

        try:
            if topic == "request_status":
                status = await self.get_app_status()
                self._send_to_client(
                    client_id,
                    {"topic": "status", "payload": status.model_dump(mode="json")},
                )
                return

            if topic == "preview/pause":
                queue = self.clients.get(client_id)
                if queue:
                    queue.paused = True
                return

            if topic == "preview/resume":
                queue = self.clients.get(client_id)
                if queue:
                    queue.paused = False
                return

            if self.session_service is None:
                self._send_to_client(
                    client_id,
                    {"topic": "error", "payload": {"error": "No active session", "topic": topic}},
                )
                return

            await self.session_service.handle_message(client_id, topic, payload)
        except (ValueError, RuntimeError) as e:
            log.warning("Client %s message '%s' rejected: %s", client_id, topic, e)
            self._send_to_client(
                client_id,
                {"topic": "error", "payload": {"error": str(e), "topic": topic}},
            )
        except Exception as e:
            log.exception("Unexpected error handling message '%s' from client %s", topic, client_id)
            self._send_to_client(
                client_id,
                {"topic": "error", "payload": {"error": str(e), "topic": topic}},
            )


class _WebSocketLogHandler(logging.Handler):
    def __init__(self, callback: Callable[[logging.LogRecord], None]) -> None:
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._callback(record)
        except Exception:
            self.handleError(record)


# ==================== Dependencies ====================


def get_app_service_websocket(websocket: WebSocket) -> AppService:
    return websocket.app.state.app_service


def get_app_service(request: Request) -> AppService:
    return request.app.state.app_service


# ==================== WebSocket ====================


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, service: AppService = Depends(get_app_service_websocket)):
    await websocket.accept()
    client_id = str(uuid.uuid4())
    queue = MsgQueue()

    await service.add_client(client_id, queue)
    shutdown = asyncio.Event()

    async def sender() -> None:
        try:
            while not shutdown.is_set():
                try:
                    result = await asyncio.wait_for(queue.drain(), timeout=0.1)
                    if result is None:
                        continue
                    msg_type, data = result
                    if msg_type == "json":
                        await websocket.send_json(data)
                    elif msg_type == "bytes":
                        await websocket.send_bytes(data)
                except TimeoutError:
                    continue
        except Exception as e:
            log.debug("Sender task ending for client %s: %s", client_id, e)
        finally:
            shutdown.set()

    async def receiver() -> None:
        try:
            while not shutdown.is_set():
                data = await websocket.receive_text()
                message = json.loads(data)
                await service.handle_client_message(client_id, message)
        except WebSocketDisconnect:
            log.debug("Client %s disconnected", client_id)
        except json.JSONDecodeError:
            log.exception("Invalid JSON from client %s", client_id)
        except Exception as e:
            log.debug("Receiver task ending for client %s: %s", client_id, e)
        finally:
            shutdown.set()

    try:
        await asyncio.gather(sender(), receiver())
    except asyncio.CancelledError:
        log.debug("WebSocket tasks cancelled for client %s", client_id)
    finally:
        shutdown.set()
        service.remove_client(client_id)
        # Bleaching safety: if nobody's watching, stop the preview.
        # No broadcast — clients are gone anyway.
        if len(service.clients) == 0 and service.session_service:
            try:
                log.info("Last client disconnected, stopping preview")
                await service.session_service.stop_preview_for_idle()
            except Exception as e:
                log.warning("Error stopping preview on idle: %s", e)


# ==================== REST ====================


@router.get("/status")
async def get_status(service: Annotated[AppService, Depends(get_app_service)]) -> AppStatusUpdate:
    return await service.get_app_status()


@router.get("/templates")
async def list_templates(service: Annotated[AppService, Depends(get_app_service)]) -> list[TemplateInfo]:
    return service.voxel_app.catalog.list_templates()


@router.get("/data-roots")
async def list_data_roots(service: Annotated[AppService, Depends(get_app_service)]) -> list[DataRoot]:
    return service.voxel_app.data_roots


@router.get("/sessions")
async def list_sessions(
    service: Annotated[AppService, Depends(get_app_service)],
    collection: str | None = None,
) -> list[SessionListing]:
    sessions = service.voxel_app.catalog.list_sessions()
    if collection is not None:
        sessions = [s for s in sessions if s.config and s.config.get("info", {}).get("collection") == collection]
    return sessions


@router.post("/session")
async def create_session(
    request: CreateSessionRequest,
    service: Annotated[AppService, Depends(get_app_service)],
) -> AppStatusUpdate:
    try:
        await service.create_session(request)
        return await service.get_app_status()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/session/close")
async def close_session(service: Annotated[AppService, Depends(get_app_service)]) -> AppStatusUpdate:
    try:
        await service.close_session()
        return await service.get_app_status()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        log.exception("Failed to close session")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "Voxel API"}


@router.get("/colormaps")
async def get_colormaps() -> list[ColormapGroup]:
    """Static colormap catalog. Moved from the old /rig/colormaps."""
    return get_colormap_catalog()


@router.get("/metadata/schemas")
async def get_metadata_schemas() -> dict[str, Any]:
    return {"schemas": discover_metadata_schema()}


@router.get("/metadata/schema")
async def get_metadata_schema(target: str) -> dict[str, Any]:
    try:
        cls = resolve_metadata_class(target)
        return cls.model_json_schema()
    except (ImportError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
