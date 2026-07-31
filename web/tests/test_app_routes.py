import datetime
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from vxl_catalog import (
    AcquisitionManifest,
    AcquisitionOrigin,
    AcquisitionVolume,
    Catalog,
    FileCatalogBackend,
    StorageSpec,
)
from vxl_web.app import create_app
from vxl_web.router import get_acquisition, get_active_acquisition, get_discovery, list_acquisitions

from vxl.app import Discovered
from vxl.instrument import ActiveAcquisitionState, VolumeProgress
from vxlib import Cell


def _catalog(tmp_path: Path) -> Catalog:
    return Catalog(
        FileCatalogBackend(tmp_path / "catalog"),
        resolve_root=lambda spec: tmp_path / "data" / spec.path.as_posix(),
    )


def _web_app(catalog: Catalog) -> Any:
    return SimpleNamespace(
        catalog=catalog,
        remotes={},
        discover=lambda: Discovered(instruments={}, templates={}),
    )


async def test_discovery_composes_bounded_application_resources(tmp_path: Path) -> None:
    voxel_app = _web_app(_catalog(tmp_path))

    discovery = await get_discovery(cast("Any", voxel_app))
    payload = discovery.model_dump(mode="json")

    assert set(payload) == {"instruments", "templates", "remotes", "colormaps", "metadata_schemas"}
    assert payload["instruments"] == {}
    assert payload["templates"] == {}
    assert payload["remotes"] == {}
    assert payload["colormaps"]
    assert "Base" in payload["metadata_schemas"]

    web_app = create_app(cast("Any", voxel_app), serve_static=False)
    paths = set(web_app.openapi()["paths"])
    assert "/api/discovery" in paths
    assert set(web_app.openapi()["paths"]["/api/instrument/acquisition"]) >= {"get", "post"}
    assert "/api/catalog/colormaps" not in paths


async def test_acquisition_history_routes_list_and_get_manifests(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    manifest = AcquisitionManifest(
        id=uuid4(),
        instrument="scope",
        origin=AcquisitionOrigin(host="controller", operator="operator"),
        created_at=datetime.datetime.now(tz=datetime.UTC),
        storage=StorageSpec(path=PurePosixPath("run")),
        bench_snapshot={},
        hardware_snapshot={},
        volumes=[AcquisitionVolume(task="task-a", profile="488")],
    )
    await catalog.create(manifest)
    app = _web_app(catalog)

    listed = await list_acquisitions(cast("Any", app))
    fetched = await get_acquisition(manifest.id, cast("Any", app))

    assert [item.id for item in listed] == [manifest.id]
    assert fetched.id == manifest.id
    with pytest.raises(HTTPException) as caught:
        await get_acquisition(uuid4(), cast("Any", app))
    assert caught.value.status_code == 404


async def test_active_acquisition_route_returns_retained_instrument_state() -> None:
    manifest = AcquisitionManifest(
        id=uuid4(),
        instrument="scope",
        origin=AcquisitionOrigin(host="controller", operator="operator"),
        created_at=datetime.datetime.now(tz=datetime.UTC),
        storage=StorageSpec(path=PurePosixPath("run")),
        bench_snapshot={},
        hardware_snapshot={},
        volumes=[AcquisitionVolume(task="task-a", profile="488")],
    )
    active = ActiveAcquisitionState(
        manifest=manifest,
        progress=VolumeProgress(
            task="task-a",
            profile="488",
            frames_captured=12,
            frames_total=48,
        ),
    )
    acquisition = Cell[ActiveAcquisitionState | None](active)
    instrument = SimpleNamespace(acquisition=acquisition)

    assert await get_active_acquisition(cast("Any", instrument)) == active

    await acquisition.set(None)
    assert await get_active_acquisition(cast("Any", instrument)) is None
