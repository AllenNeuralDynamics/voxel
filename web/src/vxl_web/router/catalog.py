"""Catalog router — discovery endpoints, no active session required.

Read-only REST shells over `voxel_app.catalog`, configured data roots, the
static colormap registry, and metadata-class introspection. No service class —
nothing here owns state or subscriptions.
"""

from typing import Any

from fastapi import APIRouter, HTTPException

from vxl.metadata import discover_metadata_schema, resolve_metadata_class
from vxl.store import SessionListing, TemplateInfo
from vxl.system import DataRoot
from vxlib import ColormapGroup, get_colormap_catalog

from ._deps import AppDep

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/sessions")
async def list_sessions(app: AppDep, collection: str | None = None) -> list[SessionListing]:
    sessions = app.voxel_app.catalog.list_sessions()
    if collection is not None:
        sessions = [s for s in sessions if s.config and s.config.get("info", {}).get("collection") == collection]
    return sessions


@router.get("/templates")
async def list_templates(app: AppDep) -> list[TemplateInfo]:
    return app.voxel_app.catalog.list_templates()


@router.get("/data-roots")
async def list_data_roots(app: AppDep) -> list[DataRoot]:
    return app.voxel_app.data_roots


@router.get("/colormaps")
async def list_colormaps() -> list[ColormapGroup]:
    return get_colormap_catalog()


@router.get("/metadata/schemas")
async def list_metadata_schemas() -> dict[str, Any]:
    return {"schemas": discover_metadata_schema()}


@router.get("/metadata/schema")
async def get_metadata_schema(target: str) -> dict[str, Any]:
    try:
        cls = resolve_metadata_class(target)
        return cls.model_json_schema()
    except (ImportError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
