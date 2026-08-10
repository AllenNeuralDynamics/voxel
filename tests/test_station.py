from pathlib import Path
from uuid import UUID

import pytest

from vxl import system as system_module
from vxl.system import Station, StationNotConfiguredError, System


@pytest.fixture(autouse=True)
def voxel_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / ".voxel"
    monkeypatch.setattr(system_module, "_voxel_home", lambda: home)
    for name in (
        "VOXEL_STORE",
        "VOXEL_SCRATCH",
        "VOXEL_MAX_RAM_FRACTION",
        "VOXEL_REMOTES",
        "VOXEL_SCHEMA_VERSION",
        "VOXEL_ID",
        "VOXEL_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    return home


def test_system_uses_env_over_whole_station_file_over_system_file(
    voxel_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = voxel_home
    home.mkdir()
    (home / "system.yaml").write_text(
        "store: /system-store\nscratch: /system-scratch\nmax_ram_fraction: 0.5\n",
        encoding="utf-8",
    )
    (home / "station.yaml").write_text(
        "schema_version: 1\nid: 12345678-1234-5678-1234-567812345678\n"
        "name: scope\nstore: /station-store\nmax_ram_fraction: 0.6\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VOXEL_STORE", "/env-store")

    system = System()

    assert system.store == Path("/env-store")
    assert system.scratch == home / "scratch"
    assert system.max_ram_fraction == 0.6


def test_station_load_requires_station_yaml(voxel_home: Path) -> None:
    del voxel_home
    with pytest.raises(StationNotConfiguredError, match="vxl station init"):
        Station.load()


def test_station_initialize_promotes_system_config_and_preserves_file_identity(
    voxel_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = voxel_home
    home.mkdir()
    (home / "system.yaml").write_text(
        "store: /node-store\nscratch: /node-scratch\nmax_ram_fraction: 0.6\n",
        encoding="utf-8",
    )
    station_id = UUID("12345678-1234-5678-1234-567812345678")

    Station.initialize("scope-a", station_id=station_id)
    monkeypatch.setenv("VOXEL_NAME", "ambient-name")
    monkeypatch.setenv("VOXEL_STORE", "/env-store")
    loaded = Station.load()

    assert loaded.info.model_dump(mode="json") == {"id": str(station_id), "name": "scope-a"}
    assert loaded.store == Path("/env-store")
    assert loaded.scratch == Path("/node-scratch")
    assert loaded.max_ram_fraction == 0.6
    assert (home / "system.yaml").is_file()
    assert (home / "station.yaml").is_file()

    with pytest.raises(FileExistsError, match="already configured"):
        Station.initialize("scope-b")
