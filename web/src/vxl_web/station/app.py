"""FastAPI composition for the Station-backed web application."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
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

from vxl.errors import InstrumentBusyError, OperationRejectedError, StartupError
from vxl.station import InstrumentTemplates, Station
from vxl.system import StationConfig, load_voxel_env
from vxlib import configure_logging, get_local_ip, get_uvicorn_log_config

from .realtime import StationRealtime
from .router import api_router

log = logging.getLogger(__name__)


class _SPAStaticFiles(StaticFiles):
    """Serve the built SPA and reject unmatched WebSocket paths cleanly."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await super().__call__(scope, receive, send)

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code == 404:
                return await super().get_response(".", scope)
            raise


def _register_error_handlers(app: FastAPI) -> None:
    """Map expected instrument failures while leaving unexpected failures as 500s."""

    @app.exception_handler(OperationRejectedError)
    async def _on_operation_rejected(_request: Request, error: OperationRejectedError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(InstrumentBusyError)
    async def _on_instrument_busy(_request: Request, error: InstrumentBusyError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(StartupError)
    async def _on_startup_error(_request: Request, error: StartupError) -> JSONResponse:
        details: list[dict[str, Any]] = [
            violation.model_dump(mode="json", exclude_none=True) for violation in error.violations
        ]
        return JSONResponse(status_code=422, content={"detail": details})


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with app.state.station.records.logs.capture():
        log.info("Starting Station-backed Voxel web application")
        try:
            yield
        finally:
            await app.state.realtime.close()
            await app.state.station.close()
            log.info("Station-backed Voxel web application stopped")


def create_app(
    station: Station,
    templates: InstrumentTemplates | None = None,
    *,
    serve_static: bool = True,
) -> FastAPI:
    """Build the Station-backed FastAPI application from injected runtime resources."""
    app = FastAPI(title="Voxel Station API", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.station = station
    app.state.instrument_templates = templates if templates is not None else InstrumentTemplates()
    app.state.realtime = StationRealtime(station)
    _register_error_handlers(app)
    app.include_router(api_router, prefix="/api")

    static_dir = Path(__file__).parents[1] / "static"
    if serve_static and static_dir.is_dir():
        app.mount("/", _SPAStaticFiles(directory=static_dir, html=True), name="static")
    return app


def serve(*, host: str, port: int = 8000, debug: bool = False) -> None:
    """Run the Station-backed Voxel web application as the sole hardware owner."""
    load_voxel_env()
    console_level = logging.DEBUG if debug else logging.INFO
    configure_logging(level=console_level, fmt="%(message)s", datefmt="[%X]")
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
        create_app(Station(StationConfig.load())),
        host=host,
        port=port,
        log_config=get_uvicorn_log_config(),
        loop="auto",
        ws_ping_interval=None,
    )


__all__ = ["create_app", "serve"]
