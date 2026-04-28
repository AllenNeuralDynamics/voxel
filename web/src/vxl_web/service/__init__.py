"""AppService — orchestrator that owns the bus, log capture, and session lifecycle.

Pure orchestrator: no routes, no WS endpoints (those live in
:mod:`vxl_web.routers`), no legacy queue infrastructure. Just the state machine
that holds the optional ``session_service``, exposes it to routes via
``request.app.state``, and broadcasts ``app.*`` events.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from vxl.app import VoxelApp
from vxl_web.protocol import AppStatus, AppStatusUpdate, ErrorEvent, LogMessage
from vxl_web.protocol.session import CreateSessionRequest
from vxl_web.wire import MsgBus
from vxlib import fire_and_forget

from .session import SessionService

log = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


class _WebSocketLogHandler(logging.Handler):
    def __init__(self, callback: Callable[[logging.LogRecord], None]) -> None:
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._callback(record)
        except Exception:
            self.handleError(record)


class AppService:
    """Holds session lifecycle + bus + log capture for the running app."""

    def __init__(self, voxel_app: VoxelApp) -> None:
        self.voxel_app = voxel_app
        self.session_service: SessionService | None = None
        self.bus = MsgBus()
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
            self.bus.broadcast("app.log.message", log_msg)

        self._log_handler = _WebSocketLogHandler(_broadcast_log)
        self._log_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(self._log_handler)

    def teardown_log_capture(self) -> None:
        if self._log_handler:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None

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

    async def broadcast_status(self) -> None:
        async with self._status_lock:
            try:
                status = await self.get_app_status()
                self.bus.broadcast("app.status", status)
            except Exception as e:
                log.warning("Failed to broadcast status: %s", e)

    # ==================== Session lifecycle ====================

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
        await self.broadcast_status()

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

                self.session_service = SessionService(
                    session=session,
                    bus=self.bus,
                    notify_status=self.broadcast_status,
                )
                await self.session_service.open()
                self._status = "ready"
                await self.broadcast_status()
            except Exception as e:
                log.exception("Failed to launch session")
                self.session_service = None
                self._status = "idle"
                self.bus.broadcast("app.error", ErrorEvent(error=str(e), topic="session/launch"))
                await self.broadcast_status()

        fire_and_forget(_launch_session(), log=log)

    async def close_session(self) -> None:
        """Close the active session.

        Order:
          1. Snapshot + null session_service; flip status to "idle".
          2. Broadcast idle status — session is still queryable but we ignore it.
          3. Tear down sub-services.
          4. Close backend session + rig (cluster shutdown runs here).
        """
        if self.session_service is None:
            raise RuntimeError("No active session to close")

        session_service = self.session_service
        self.session_service = None
        self._status = "idle"
        await self.broadcast_status()

        try:
            await session_service.close()
        except Exception:
            log.exception("Error closing session service")
        try:
            await self.voxel_app.close_session()
        except Exception:
            log.exception("Error closing voxel app session")


__all__ = ["AppService"]
