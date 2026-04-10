"""App-level service for Voxel.

This service manages:
- WebSocket client communication
- Log streaming from app startup
- Session lifecycle (create/resume/fork/close) via VoxelApp
- App-level status broadcasting
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
from vxl.config import DataRoot
from vxl.metadata import discover_metadata_targets, resolve_metadata_class
from vxl.store import SessionListing, TemplateInfo
from vxl_web.services.msg_queue import MsgQueue
from vxlib import fire_and_forget

from .acq import acq_router
from .rig import rig_router
from .session import SessionService, SessionStateUpdate, info_router

router = APIRouter(tags=["app"])
router.include_router(info_router)
router.include_router(acq_router)
router.include_router(rig_router)
log = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


AppStatus = Literal["idle", "launching", "ready"]


class AppStatusUpdate(BaseModel):
    """Overall application status broadcast."""

    status: AppStatus
    session: SessionStateUpdate | None = None
    timestamp: str


class LogMessage(BaseModel):
    level: str
    message: str
    logger: str
    timestamp: str


class CreateSessionRequest(BaseModel):
    """Unified request for create/resume/fork."""

    # Create from template
    template: str | None = None
    # Fork from existing session
    source_session: str | None = None
    # Resume existing session
    resume: str | None = None
    # Common fields
    data_root: str | None = None
    name: str = ""
    description: str = ""
    collection: str = ""
    clear_stacks: bool = False


class AppService:
    """App-level service managing WebSocket clients and session lifecycle.

    Delegates session lifecycle to VoxelApp. Handles WebSocket
    broadcasting and client management.
    """

    def __init__(self, voxel_app: VoxelApp):
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
        root_logger = logging.getLogger()
        root_logger.addHandler(self._log_handler)

    def teardown_log_capture(self) -> None:
        if self._log_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self._log_handler)
            self._log_handler = None

    # ==================== Client Management ====================

    def _broadcast(
        self,
        data: dict[str, Any] | bytes,
        with_status: bool = False,
        exclude: str | None = None,
    ) -> None:
        if data:
            msg_type = "bytes" if isinstance(data, bytes) else "json"
            priority = 1 if msg_type == "bytes" else 0
            for client_id, queue in self.clients.items():
                if client_id == exclude:
                    continue
                queue.put(msg_type, data, priority=priority)

        if with_status:
            self._schedule_status_broadcast()

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

    def _schedule_status_broadcast(self) -> None:
        fire_and_forget(self._broadcast_status(), log=log, timeout=5.0)

    # ==================== Session Lifecycle ====================

    async def create_session(self, request: CreateSessionRequest) -> None:
        """Create, resume, or fork a session based on request fields."""
        if self.session_service is not None:
            raise RuntimeError("A session is already active. Close it first.")

        self._status = "launching"
        await self._broadcast_status()

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
            self._status = "ready"
            await self._broadcast_status()

        except Exception:
            log.exception("Failed to create/resume session")
            self.session_service = None
            self._status = "idle"
            await self._broadcast_status()
            raise

    async def close_session(self) -> None:
        if self.session_service is None:
            raise RuntimeError("No active session to close")

        try:
            await self.session_service.rig_service.rig.stop_preview()
            await self.voxel_app.close_session()
        except Exception:
            log.exception("Error during session close")
        finally:
            self.session_service = None
            self._status = "idle"
            if self.clients:
                await self._broadcast_status()

    # ==================== Message Handling ====================

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
                    {
                        "topic": "error",
                        "payload": {"error": "No active session", "topic": topic},
                    },
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
            log.exception(
                "Unexpected error handling message '%s' from client %s",
                topic,
                client_id,
            )
            self._send_to_client(
                client_id,
                {"topic": "error", "payload": {"error": str(e), "topic": topic}},
            )


class _WebSocketLogHandler(logging.Handler):
    def __init__(self, callback: Callable[[logging.LogRecord], None]):
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
async def websocket_endpoint(websocket: WebSocket, service: AppService = Depends(get_app_service_websocket)):  # noqa: C901
    await websocket.accept()
    client_id = str(uuid.uuid4())
    queue = MsgQueue()

    await service.add_client(client_id, queue)

    shutdown = asyncio.Event()

    async def sender():
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

    async def receiver():
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
        if len(service.clients) == 0 and service.session_service:
            try:
                log.info("Last client disconnected, stopping preview")
                await service.session_service.rig_service.stop_preview()
            except Exception as e:
                log.warning(f"Error stopping preview during disconnect: {e}")


# ==================== REST Endpoints ====================


@router.get("/status")
async def get_status(
    service: Annotated[AppService, Depends(get_app_service)],
) -> AppStatusUpdate:
    return await service.get_app_status()


@router.get("/templates")
async def list_templates(
    service: Annotated[AppService, Depends(get_app_service)],
) -> list[TemplateInfo]:
    return service.voxel_app.catalog.list_templates()


@router.get("/data-roots")
async def list_data_roots(
    service: Annotated[AppService, Depends(get_app_service)],
) -> list[DataRoot]:
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
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.exception("Failed to create session")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/session/close")
async def close_session(
    service: Annotated[AppService, Depends(get_app_service)],
) -> AppStatusUpdate:
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


@router.get("/metadata/targets")
async def get_metadata_targets() -> dict:
    return {"targets": discover_metadata_targets()}


@router.get("/metadata/schema")
async def get_metadata_schema(target: str) -> dict:
    try:
        cls = resolve_metadata_class(target)
        return cls.model_json_schema()
    except (ImportError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
