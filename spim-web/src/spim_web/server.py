"""Web interface for SPIM Rig control."""

import logging
import os
from contextlib import asynccontextmanager

import zmq.asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from spim_rig import SpimRig, SpimRigConfig

from .service import RigService
from .service import router as rig_router

log = logging.getLogger("ui")


def _create_lifespan(config: SpimRigConfig):
    """Create a lifespan context manager with the given config."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan: initialize and cleanup rig."""
        # Startup: Initialize rig and services
        log.info("Initializing rig: %s", config.info.name)

        zctx = zmq.asyncio.Context()
        rig = SpimRig(zctx=zctx, config=config)
        await rig.start()

        # Store rig_service on the application state
        app.state.rig = rig
        app.state.rig_service = RigService(rig=rig)

        log.info("Rig and services initialized successfully")
        log.info("Available cameras: %s", list(rig.cameras.keys()))

        yield

        # Shutdown: Stop rig and cleanup
        log.info("Shutting down rig...")
        try:
            await app.state.rig.stop()
        except Exception as e:
            log.error("Error stopping rig: %s", e)

        log.info("Rig shutdown complete")

    return lifespan


def create_rig_app(config: SpimRigConfig, serve_static: bool = True) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: SPIM rig configuration
        serve_static: Whether to serve static UI files

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="SPIM Rig Control API",
        description="Web API for controlling SPIM microscope rigs",
        version="0.1.0",
        lifespan=_create_lifespan(config),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(rig_router)  # New unified WebSocket endpoint

    @app.get("/health")
    async def health():
        """Basic health check."""
        return {
            "status": "ok",
            "service": "SPIM Rig Control API",
        }

    if serve_static:
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.isdir(static_dir):
            app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


__all__ = ["create_rig_app"]
