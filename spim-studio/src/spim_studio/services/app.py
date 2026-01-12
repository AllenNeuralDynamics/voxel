"""App-level service for SPIM Studio.

This service manages:
- WebSocket client communication
- Log streaming from app startup
- Session lifecycle (launch/close)
- App-level status (roots, rigs, session)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from spim_rig import Session

from spim_studio.system import SessionRoot, SystemConfig, get_rig_path, list_rigs

from .session import SessionService, SessionStatus, session_router

router = APIRouter(tags=["app"])
router.include_router(session_router)  # Include session routes (requires active session)
log = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    """Return an ISO 8601 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


AppPhase = Literal["idle", "launching", "ready"]


class AppStatus(BaseModel):
    """Overall application status."""

    phase: AppPhase
    roots: list[SessionRoot]
    rigs: list[str]
    session: SessionStatus | None = None
    timestamp: str


class LogMessage(BaseModel):
    """Log message for WebSocket streaming."""

    level: str
    message: str
    logger: str
    timestamp: str


class LaunchRequest(BaseModel):
    """Request to launch a session."""

    root_name: str
    session_name: str
    rig_config: str | None = None  # None = use existing, else rig name from ~/.spim/rigs/


class AppService:
    """App-level service managing WebSocket clients and session lifecycle.

    Hierarchy: AppService → SessionService → RigService
    """

    def __init__(self, system_config: SystemConfig):
        self.system_config = system_config
        self.session_service: SessionService | None = None
        self.clients: dict[str, asyncio.Queue[tuple[str, Any]]] = {}
        self._log_handler: _WebSocketLogHandler | None = None
        self._phase: AppPhase = "idle"

        self._setup_log_capture()

    def _setup_log_capture(self) -> None:
        """Set up log capture for WebSocket streaming."""

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

        # Attach to root logger to capture all logs
        root_logger = logging.getLogger()
        root_logger.addHandler(self._log_handler)
        log.debug("Log capture enabled for WebSocket streaming")

    def _teardown_log_capture(self) -> None:
        """Remove log capture handler."""
        if self._log_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self._log_handler)
            self._log_handler = None

    # ==================== Client Management ====================

    def _broadcast(self, data: dict[str, Any] | bytes, with_status: bool = False) -> None:
        """Broadcast to all clients. Dict = JSON message, bytes = binary.

        Args:
            data: The message to broadcast.
            with_status: If True, also broadcast full app status after this message.
        """
        msg_type = "bytes" if isinstance(data, bytes) else "json"
        for queue in self.clients.values():
            try:
                queue.put_nowait((msg_type, data))
            except asyncio.QueueFull:
                pass

        if with_status:
            self._broadcast_status()

    async def _send_to_client(self, client_id: str, data: dict[str, Any]) -> None:
        """Send a message to a specific client."""
        queue = self.clients.get(client_id)
        if queue:
            try:
                await queue.put(("json", data))
            except asyncio.QueueFull:
                log.warning("Client %s queue full, dropping message", client_id)

    async def add_client(self, client_id: str, queue: asyncio.Queue[tuple[str, Any]]) -> None:
        """Register a new client and send initial status snapshot."""
        self.clients[client_id] = queue
        log.info("Client %s connected. Total: %d", client_id, len(self.clients))

        # Send initial app status
        status = self._get_app_status()
        await self._send_to_client(client_id, {"topic": "status", "payload": status.model_dump(mode="json")})

    def remove_client(self, client_id: str) -> None:
        """Remove a client from the distribution list."""
        self.clients.pop(client_id, None)
        log.info("Client %s disconnected. Total: %d", client_id, len(self.clients))

    # ==================== Status ====================

    def _get_app_status(self) -> AppStatus:
        """Get current app status."""
        session_status = None
        if self.session_service:
            session_status = self.session_service.get_status()

        return AppStatus(
            phase=self._phase,
            roots=self.system_config.session_roots,
            rigs=list_rigs(),
            session=session_status,
            timestamp=_utc_timestamp(),
        )

    def _broadcast_status(self) -> None:
        """Broadcast app status to all clients."""
        status = self._get_app_status()
        self._broadcast({"topic": "status", "payload": status.model_dump(mode="json")})

    # ==================== Session Lifecycle ====================

    async def launch_session(
        self,
        root_name: str,
        session_name: str,
        rig_config: str | None = None,
    ) -> None:
        """Launch a new session or resume an existing one."""
        if self.session_service is not None:
            raise RuntimeError("A session is already active. Close it first.")

        # Resolve session directory
        root = self.system_config.get_root(root_name)
        if root is None:
            raise ValueError(f"Session root '{root_name}' not found")

        session_dir = root.path / session_name

        # Resolve rig config path
        config_path: Path | None = None
        if rig_config:
            config_path = get_rig_path(rig_config)
            if config_path is None:
                raise ValueError(f"Rig config '{rig_config}' not found in ~/.spim/rigs/")

        # Check if this is a new session or resume
        session_file = session_dir / "session.spim.yaml"
        if session_file.exists():
            log.info(f"Resuming existing session: {session_dir}")
            config_path = None  # Use existing config
        else:
            if config_path is None:
                raise ValueError("Rig config required for new session")
            log.info(f"Creating new session: {session_dir}")
            session_dir.mkdir(parents=True, exist_ok=True)

        # Set phase to launching and broadcast
        self._phase = "launching"
        self._broadcast_status()

        # Launch the session
        try:
            session = await Session.launch(session_dir, config_path)

            # Create SessionService with broadcast callback
            self.session_service = SessionService(session=session, broadcast=self._broadcast)

            log.info(f"Session launched: {session_dir}")
            self._phase = "ready"
            self._broadcast_status()

        except Exception as e:
            log.error(f"Failed to launch session: {e}", exc_info=True)
            self.session_service = None
            self._phase = "idle"
            self._broadcast_status()
            raise

    async def close_session(self) -> None:
        """Close the current session."""
        if self.session_service is None:
            raise RuntimeError("No active session to close")

        try:
            # Stop preview if running
            if self.session_service.rig_service.is_previewing:
                await self.session_service.rig_service.rig.stop_preview()

            # Stop the rig
            await self.session_service.session.rig.stop()

            log.info(f"Session closed: {self.session_service.session.session_dir}")

        except Exception as e:
            log.error(f"Error during session close: {e}", exc_info=True)
        finally:
            self.session_service = None
            self._phase = "idle"
            self._broadcast_status()

    # ==================== Message Handling ====================

    async def handle_client_message(self, client_id: str, message: dict[str, Any]) -> None:
        """Handle incoming message from a client."""
        topic = message.get("topic")
        payload = message.get("payload", {})

        if not topic:
            log.warning("Received message without topic from client %s", client_id)
            return

        try:
            # App-level topics
            if topic == "request_status":
                status = self._get_app_status()
                await self._send_to_client(client_id, {"topic": "status", "payload": status.model_dump(mode="json")})
                return

            # Session-level topics - delegate to session service
            if self.session_service is None:
                log.warning("No active session for topic %s from client %s", topic, client_id)
                await self._send_to_client(
                    client_id,
                    {"topic": "error", "payload": {"error": "No active session", "topic": topic}},
                )
                return

            await self.session_service.handle_message(client_id, topic, payload)

        except Exception as e:
            log.error("Error handling message from client %s: %s", client_id, e, exc_info=True)
            await self._send_to_client(
                client_id,
                {"topic": "error", "payload": {"error": str(e), "topic": topic}},
            )


class _WebSocketLogHandler(logging.Handler):
    """Log handler that broadcasts to WebSocket clients."""

    def __init__(self, callback: Callable[[logging.LogRecord], None]):
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._callback(record)
        except Exception:
            self.handleError(record)


# ==================== WebSocket Endpoint ====================


def get_app_service_websocket(websocket: WebSocket) -> AppService:
    """Dependency helper for WebSocket routes."""
    return websocket.app.state.app_service


def get_app_service(request: Request) -> AppService:
    """Dependency helper for HTTP routes."""
    return request.app.state.app_service


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, service: AppService = Depends(get_app_service_websocket)):
    """Unified WebSocket endpoint for all app, session, and rig communication."""
    await websocket.accept()
    client_id = str(uuid.uuid4())
    message_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=100)

    await service.add_client(client_id, message_queue)

    shutdown = asyncio.Event()

    async def sender():
        """Send messages from queue to client."""
        try:
            while not shutdown.is_set():
                try:
                    msg_type, data = await asyncio.wait_for(message_queue.get(), timeout=0.1)
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
        """Receive messages from client."""
        try:
            while not shutdown.is_set():
                data = await websocket.receive_text()
                message = json.loads(data)
                await service.handle_client_message(client_id, message)
        except WebSocketDisconnect:
            log.debug("Client %s disconnected", client_id)
        except json.JSONDecodeError as e:
            log.error("Invalid JSON from client %s: %s", client_id, e)
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
        # Auto-stop preview if this was a client that requested it
        if service.session_service and service.session_service.rig_service.preview_start_count > 0:
            try:
                await service.session_service.rig_service.force_stop_preview()
            except Exception as e:
                log.warning(f"Error stopping preview during disconnect: {e}")


# ==================== REST Endpoints ====================


@router.get("/status")
async def get_status(service: AppService = Depends(get_app_service)) -> AppStatus:
    """Get current app status including session if active."""
    return service._get_app_status()


@router.get("/roots/{root_name}/sessions")
async def list_sessions(root_name: str, service: AppService = Depends(get_app_service)) -> dict:
    """List sessions in a root."""
    try:
        sessions = service.system_config.list_sessions(root_name)
        return {
            "sessions": [s.model_dump(mode="json") for s in sessions],
            "count": len(sessions),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/session/launch")
async def launch_session(request: LaunchRequest, service: AppService = Depends(get_app_service)) -> AppStatus:
    """Launch a new session or resume an existing one."""
    try:
        await service.launch_session(
            root_name=request.root_name,
            session_name=request.session_name,
            rig_config=request.rig_config,
        )
        return service._get_app_status()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"Failed to launch session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session")
async def close_session(service: AppService = Depends(get_app_service)) -> AppStatus:
    """Close the current session."""
    try:
        await service.close_session()
        return service._get_app_status()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        log.error(f"Failed to close session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
