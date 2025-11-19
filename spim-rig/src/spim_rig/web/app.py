"""FastAPI application for SPIM Rig web control."""

import os
import logging
from contextlib import asynccontextmanager

import zmq.asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from spim_rig import SpimRig, SpimRigConfig
from spim_rig.web.service import RigService
from spim_rig.web.service import router as rig_router

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

        # Store rig_service on the application state
        app.state.rig = rig
        app.state.rig_service = RigService(rig=rig)

        log.info("Rig and services initialized successfully")
        log.info("Available cameras: %s", list(rig.cameras.keys()))

        yield

        # Shutdown: Stop preview and cleanup
        log.info("Shutting down rig...")
        try:
            if app.state.rig.preview.is_active:
                await app.state.rig.stop_preview()
        except Exception as e:
            log.error("Error stopping preview: %s", e)

        log.info("Rig shutdown complete")

    return lifespan




def create_app(config_path: str, serve_static: bool = True) -> FastAPI:
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
