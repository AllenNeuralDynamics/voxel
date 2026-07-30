"""FastAPI factory + launcher for the Voxel web backend, on the ``vxl.Instrument`` API.

Lean by design: two routers (the ``VoxelApp`` surface — discovery/launch/close/history — and the active
``Instrument`` surface), the per-instrument WS feed (:mod:`vxl_web.live`), and the ``MsgBus``
(:mod:`vxl_web.wire`). No manager/service layer — routers call the ``Instrument``'s flat method surface
directly, so the only lifetime-scoped object is the ``InstrumentFeed``. The previous stack lives under
:mod:`vxl_web._classic`.

Runs as a single uvicorn process: it owns the open hardware, the bus, and one event loop, so there is
exactly one process per microscope (never multiple workers — they would each open the hardware).
"""

import asyncio
import logging
from collections import deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from vxl.app import VoxelApp
from vxl.errors import InstrumentBusyError, OperationRejectedError, StartupError
from vxl.system import load_voxel_env
from vxlib import configure_logging, get_local_ip, get_uvicorn_log_config

from .live import AppFeed, LogMessage
from .router import api_router
from .wire import MsgBus

log = logging.getLogger(__name__)

LOG_BUFFER_SIZE = 1000  # recent records retained for client backlog on (re)connect


class SPAStaticFiles(StaticFiles):
    """StaticFiles with SPA fallback: serve index.html for unknown HTTP paths, and close stray
    WebSocket scopes with 1008 rather than tripping the HTTP-only assertion."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await super().__call__(scope, receive, send)

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as e:
            if e.status_code == 404:
                return await super().get_response(".", scope)
            raise


def _register_error_handlers(app: FastAPI) -> None:
    """Map expected instrument failures to HTTP while leaving unexpected errors as 500s."""

    def details(exc: StartupError) -> list[dict[str, Any]]:
        return [violation.model_dump(mode="json", exclude_none=True) for violation in exc.violations]

    @app.exception_handler(OperationRejectedError)
    async def _on_operation_rejected(_request: Request, exc: OperationRejectedError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(InstrumentBusyError)
    async def _on_instrument_busy(_request: Request, exc: InstrumentBusyError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(StartupError)
    async def _on_startup_error(_request: Request, exc: StartupError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": details(exc)})


class _LogHandler(logging.Handler):
    """Root-logger handler that buffers records for replay and streams them to the bus. ``emit`` runs on
    whatever thread logged, so it only captures fields — sequencing, buffering, and delivery are marshalled
    onto the loop (the seq counter, buffer, and bus may only be touched from its loop)."""

    def __init__(self, loop: asyncio.AbstractEventLoop, bus: MsgBus, buffer: deque[LogMessage]) -> None:
        super().__init__()
        self._loop = loop
        self._bus = bus
        self._buffer = buffer
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            fields = (record.levelname.lower(), record.getMessage(), record.name, datetime.now(UTC).isoformat())
        except Exception:
            self.handleError(record)
            return
        self._loop.call_soon_threadsafe(self._deliver, *fields)

    def _deliver(self, level: str, message: str, logger: str, timestamp: str) -> None:
        """On the loop: assign the next seq, buffer the record for backlog, then broadcast it live."""
        self._seq += 1
        msg = LogMessage(seq=self._seq, level=level, message=message, logger=logger, timestamp=timestamp)
        self._buffer.append(msg)
        self._bus.broadcast("logs", msg)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    log.info("Starting Voxel web backend")
    handler = _LogHandler(asyncio.get_running_loop(), app.state.bus, app.state.log_buffer)
    handler.setLevel(logging.DEBUG)  # stream everything to the UI; the client filters by level
    logging.getLogger().addHandler(handler)
    feed = AppFeed(app.state.voxel_app, app.state.bus)  # publishes app.status + owns the InstrumentFeed lifecycle
    feed.attach()
    try:
        yield
    finally:
        feed.detach()
        logging.getLogger().removeHandler(handler)  # stop streaming logs to clients
        await app.state.voxel_app.close()  # parks hardware on shutdown (closes the active instrument, if any)
        log.info("Voxel web backend stopped")


def create_app(voxel_app: VoxelApp | None = None, *, serve_static: bool = True) -> FastAPI:
    """Build the FastAPI app. ``voxel_app`` defaults to a fresh ``VoxelApp``; ``serve_static`` mounts the
    built UI at ``/`` (pass ``False`` for API-only test clients)."""
    app = FastAPI(title="Voxel API", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.voxel_app = voxel_app or VoxelApp()
    app.state.bus = MsgBus()
    app.state.log_buffer = deque(maxlen=LOG_BUFFER_SIZE)
    _register_error_handlers(app)
    app.include_router(api_router, prefix="/api")
    if serve_static and (static_dir := Path(__file__).parent / "static").is_dir():
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="static")
    return app


def serve(*, host: str, port: int = 8000, debug: bool = False) -> None:
    """Run the Voxel web application."""
    load_voxel_env()  # ambient env from ~/.voxel/.env before anything reads it (System, S3 clients)
    console_level = logging.DEBUG if debug else logging.INFO
    configure_logging(level=console_level, fmt="%(message)s", datefmt="[%X]")
    # The WS log feed streams DEBUG to the UI while the console keeps the user-facing threshold. Per-handler
    # levels split the two: the bus handler (added in the lifespan) is DEBUG; the console handler is
    # console_level. Without --debug, only the Voxel packages emit DEBUG (root stays INFO) so the feed isn't
    # flooded with third-party library noise; --debug opens everything, including third-party loggers.
    root_logger = logging.getLogger()
    if debug:
        root_logger.setLevel(logging.DEBUG)
    else:
        root_logger.setLevel(logging.INFO)
        for name in ("vxl", "vxlib", "rigup", "vxl_web", "vxl_drivers"):
            logging.getLogger(name).setLevel(logging.DEBUG)
    for handler in root_logger.handlers:
        handler.setLevel(console_level)
    log.info("Starting Voxel...")
    log.info("Web UI: http://localhost:%d", port)
    if (local_ip := get_local_ip()) != "127.0.0.1":
        log.info("      or http://%s:%d", local_ip, port)
    uvicorn.run(
        create_app(),
        host=host,
        port=port,
        log_config=get_uvicorn_log_config(),
        loop="auto",
        ws_ping_interval=None,  # disable keepalive pings — prevents a race with manual send_bytes
    )
