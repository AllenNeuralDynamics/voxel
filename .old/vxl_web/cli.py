"""

Entry point for web interface.

Always starts in lobby mode. Sessions are launched via the API.

Examples:
    # Start in lobby mode (default)
    vxl

    # Start with debug logging
    vxl --debug

    # Start on a different port
    vxl --port 9000

    # Start server and open a native webview window
    vxl --view
"""

import argparse
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from vxl.app import VoxelApp
from vxlib import configure_logging, get_local_ip, get_uvicorn_log_config

from .services import AppService, app_router

log = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """StaticFiles with SPA fallback — serves index.html for unknown paths."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as e:
            if e.status_code == 404:
                return await super().get_response(".", scope)
            raise


def _create_lifespan(voxel_app: VoxelApp) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("Starting Voxel in lobby mode")

        app_service = AppService(voxel_app)
        app.state.app_service = app_service

        log.info("Available data roots: %s", [r.name for r in voxel_app.data_roots])

        yield

        if app_service.session_service is not None:
            log.info("Closing active session...")
            try:
                await app_service.close_session()
            except Exception:
                log.exception("Error closing session")

        app_service.teardown_log_capture()
        log.info("Voxel stopped")

    return lifespan


def create_app(voxel_app: VoxelApp | None = None, serve_static: bool = True) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        voxel_app: VoxelApp instance. If None, creates one with default YAML catalog.
        serve_static: Whether to serve static UI files.
    """
    if voxel_app is None:
        voxel_app = VoxelApp()

    app = FastAPI(
        title="Voxel API",
        description="Web API for Voxel microscope control",
        version="0.1.0",
        lifespan=_create_lifespan(voxel_app),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(app_router, prefix="/api")

    if serve_static:
        static_dir = Path(__file__).parent / "static"
        if static_dir.is_dir():
            app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="static")

    return app


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="vxl",
        description="Voxel - Microscope Control System",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for web server (default: 8000)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main() -> None:
    """Main entry point for voxel CLI."""
    parser = create_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    configure_logging(level=log_level, fmt="%(message)s", datefmt="[%X]")
    log = logging.getLogger("vxl")

    log.info("Starting Voxel...")

    app = create_app()

    url = f"http://localhost:{args.port}"
    local_ip = get_local_ip()
    log.info("Web UI: %s", url)
    if local_ip != "127.0.0.1":
        log.info("      or http://%s:%d", local_ip, args.port)

    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104 :: allow bind all
        port=args.port,
        log_config=get_uvicorn_log_config(),
        loop="auto",
        ws_ping_interval=None,  # disable keepalive pings — prevents race with send_bytes
    )


if __name__ == "__main__":
    main()
