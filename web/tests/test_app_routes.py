from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from vxl_records import AcquisitionCatalog, SQLiteRecords
from vxl_web.app import create_app
from vxl_web.router import get_acquisition, get_discovery

from vxl.app import Discovered


def _catalog(tmp_path: Path) -> AcquisitionCatalog:
    return SQLiteRecords(
        tmp_path / "records.sqlite3",
        resolve_root=lambda spec: tmp_path / "data" / spec.path.as_posix(),
    ).acquisitions


def _web_app(catalog: AcquisitionCatalog) -> Any:
    return SimpleNamespace(
        records=SimpleNamespace(acquisitions=catalog),
        remotes={},
        station_config=SimpleNamespace(info={"id": UUID("12345678-1234-5678-1234-567812345678"), "name": "scope"}),
        discover=lambda: Discovered(instruments={}, templates={}),
    )


def _request(app: FastAPI) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("testserver", 80),
            "root_path": "",
            "path": "/api/discovery",
            "headers": [],
            "router": app.router,
        }
    )


async def test_discovery_composes_bounded_application_resources(tmp_path: Path) -> None:
    voxel_app = _web_app(_catalog(tmp_path))
    web_app = create_app(cast("Any", voxel_app), serve_static=False)

    discovery = await get_discovery(_request(web_app), cast("Any", voxel_app))
    payload = discovery.model_dump(mode="json")

    assert set(payload) == {
        "station",
        "instruments",
        "templates",
        "remotes",
        "colormaps",
        "metadata_schemas",
        "preview",
    }
    assert payload["station"] == {"id": "12345678-1234-5678-1234-567812345678", "name": "scope"}
    assert payload["instruments"] == {}
    assert payload["templates"] == {}
    assert payload["remotes"] == {}
    assert payload["colormaps"]
    assert "Base" in payload["metadata_schemas"]
    assert payload["preview"] == {
        "websocket_url": "ws://testserver/api/preview/ws",
        "protocol_version": 1,
    }

    paths = set(web_app.openapi()["paths"])
    assert "/api/discovery" in paths
    assert set(web_app.openapi()["paths"]["/api/instrument/acquisition"]) >= {"get", "post"}
    assert "/api/catalog/colormaps" not in paths


async def test_missing_acquisition_is_mapped_to_not_found(tmp_path: Path) -> None:
    app = _web_app(_catalog(tmp_path))

    with pytest.raises(HTTPException) as caught:
        await get_acquisition(uuid4(), cast("Any", app))
    assert caught.value.status_code == 404
