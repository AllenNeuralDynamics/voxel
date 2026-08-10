from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from vxl_catalog import Catalog, FileCatalogBackend

from vxl import app as app_module
from vxl.instrument import Instrument


async def test_voxel_app_owns_and_passes_catalog_to_launched_instrument(monkeypatch, tmp_path: Path) -> None:
    station = SimpleNamespace(
        dir=tmp_path / ".voxel",
        remotes={},
        info=SimpleNamespace(id=uuid4(), name="test"),
    )
    catalog = Catalog(
        FileCatalogBackend(tmp_path / "catalog"),
        resolve_root=lambda _spec: tmp_path / "acquisition",
    )
    app = app_module.VoxelApp(catalog=catalog, station=station)
    instrument_home = app.instruments_dir / "scope.voxel"
    instrument_home.mkdir()
    captured: dict[str, object] = {}

    class FakeInstrument:
        path = instrument_home

        async def open(self) -> None:
            return

        async def close(self) -> None:
            return

    def from_path(home: Path, *, catalog: Catalog) -> FakeInstrument:
        captured["home"] = home
        captured["catalog"] = catalog
        return FakeInstrument()

    monkeypatch.setattr(Instrument, "from_path", staticmethod(from_path))

    launched = await app.launch("scope")

    assert app.catalog is catalog
    assert launched.path == instrument_home
    assert captured == {"home": instrument_home, "catalog": catalog}
