"""FastAPI application for SPIM Rig web control."""

import asyncio
import logging
from contextlib import asynccontextmanager

import zmq.asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from spim_rig import SpimRig, SpimRigConfig
from spim_rig.web.routers.preview import router as preview_router

# Global state
_rig: SpimRig | None = None
_preview_clients: dict[str, asyncio.Queue] = {}

log = logging.getLogger("ui")


def create_lifespan(config_path: str):
    """Create a lifespan context manager with the given config path."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan: initialize and cleanup rig."""
        global _rig

        # Startup: Initialize rig
        log.info("Loading rig configuration from: %s", config_path)

        config = SpimRigConfig.from_yaml(config_path)
        zctx = zmq.asyncio.Context()
        _rig = SpimRig(zctx, config)
        await _rig.start()

        log.info("Rig initialized successfully")
        log.info("Available cameras: %s", list(_rig.cameras.keys()))

        yield

        # Shutdown: Stop preview and cleanup
        log.info("Shutting down rig...")
        if _rig:
            try:
                await _rig.stop_preview()
            except Exception as e:
                log.error("Error stopping preview: %s", e)

        log.info("Rig shutdown complete")

    return lifespan


def create_app(config_path: str) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config_path: Path to the SPIM rig configuration YAML file

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="SPIM Rig Control API",
        description="Web API for controlling SPIM microscope rigs",
        version="0.1.0",
        lifespan=create_lifespan(config_path),
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins in development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(preview_router)

    # Basic health check endpoint
    @app.get("/")
    async def root():
        """Root endpoint - basic health check."""
        return {
            "status": "ok",
            "service": "SPIM Rig Control API",
            "cameras": list(_rig.cameras.keys()) if _rig else [],
        }

    return app


# Dependency injection functions
def get_rig() -> SpimRig:
    """Get the initialized SpimRig instance."""
    if _rig is None:
        raise HTTPException(status_code=503, detail="Rig not initialized")
    return _rig


def get_preview_clients() -> dict[str, asyncio.Queue]:
    """Get the preview clients dictionary."""
    return _preview_clients
