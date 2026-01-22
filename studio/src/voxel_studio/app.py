"""Web interface for Voxel Studio.

Always starts in lobby mode. Sessions are launched via the API.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .services import AppService, app_router
from .system import SystemConfig

log = logging.getLogger(__name__)


def _create_lifespan(system_config: SystemConfig):
    """Create a lifespan context manager for the app."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan: initialize and cleanup."""
        log.info("Starting Voxel Studio in lobby mode")

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
            except Exception as e:
                log.error("Error closing session: %s", e)

        # Cleanup log handler
        app_service._teardown_log_capture()
        log.info("Voxel Studio stopped")

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
        title="Voxel Studio API",
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
    async def health():
        """Basic health check."""
        return {
            "status": "ok",
            "service": "Voxel Studio API",
        }

    if serve_static:
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.isdir(static_dir):
            app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


__all__ = ["create_app"]
