"""FastAPI application for SPIM Rig web control."""

import logging
from contextlib import asynccontextmanager

import zmq.asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from spim_rig import SpimRig, SpimRigConfig
from spim_rig.web.preview import PreviewService
from spim_rig.web.preview import router as preview_router

log = logging.getLogger("ui")


def create_lifespan(config_path: str):
    """Create a lifespan context manager with the given config path."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan: initialize and cleanup rig."""
        # Startup: Initialize rig and services
        log.info("Loading rig configuration from: %s", config_path)

        config = SpimRigConfig.from_yaml(config_path)
        zctx = zmq.asyncio.Context()
        rig = SpimRig(zctx, config)
        await rig.start()

        # Store rig and services on the application state to avoid globals
        app.state.rig = rig
        app.state.preview_service = PreviewService(rig=rig)

        log.info("Rig and services initialized successfully")
        log.info("Available cameras: %s", list(rig.cameras.keys()))

        yield

        # Shutdown: Stop preview and cleanup
        log.info("Shutting down rig...")
        if hasattr(app.state, "rig") and app.state.rig:
            try:
                if app.state.rig.preview.is_active:
                    await app.state.rig.stop_preview()
            except Exception as e:
                log.error("Error stopping preview: %s", e)

        log.info("Rig shutdown complete")

    return lifespan


def create_app(config_path: str) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="SPIM Rig Control API",
        description="Web API for controlling SPIM microscope rigs",
        version="0.1.0",
        lifespan=create_lifespan(config_path),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(preview_router)

    @app.get("/")
    async def root():
        """Root endpoint - basic health check."""
        # Note: This still relies on app.state.rig being available
        # A dependency-injected approach would be better in the long run
        return {
            "status": "ok",
            "service": "SPIM Rig Control API",
            "cameras": list(app.state.rig.cameras.keys()) if hasattr(app.state, "rig") else [],
        }

    return app
