"""Web interface for Voxel.

Always starts in lobby mode. Sessions are launched via the API.
"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from vxl.system import SystemConfig

from .services import AppService, app_router

log = logging.getLogger(__name__)


def _create_lifespan(system_config: SystemConfig) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Create a lifespan context manager for the app."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Application lifespan: initialize and cleanup."""
        log.info("Starting Voxel in lobby mode")

        # Create app service (starts with no session)
        app_service = AppService(system_config)

        # Store on application state
        app.state.system_config = system_config
        app.state.app_service = app_service

        log.info("Available session roots: %s", [r.name for r in system_config.session_roots])

        yield

        # Shutdown: Close any active session
        if app_service.session_service is not None:
            log.info("Closing active session...")
            try:
                await app_service.close_session()
            except Exception:
                log.exception("Error closing session")

        # Cleanup log handler
        app_service.teardown_log_capture()
        log.info("Voxel stopped")

    return lifespan


def create_app(system_config: SystemConfig | None = None, serve_static: bool = True) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        system_config: System configuration. If None, loads from ~/.voxel/system.yaml.
        serve_static: Whether to serve static UI files.

    Returns:
        Configured FastAPI application.
    """
    if system_config is None:
        system_config = SystemConfig.load()

    app = FastAPI(
        title="Voxel API",
        description="Web API for Voxel microscope control",
        version="0.1.0",
        lifespan=_create_lifespan(system_config),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include app router (includes session and rig routes)
    app.include_router(app_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Basic health check."""
        return {
            "status": "ok",
            "service": "Voxel API",
        }

    if serve_static:
        static_dir = Path(__file__).parent / "static"
        if static_dir.is_dir():
            app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


__all__ = ["create_app"]
