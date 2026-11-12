from pathlib import Path
from uuid import UUID

import pytest

from vxl.core.errors import StationNotConfiguredError
from vxl.core.station import StationConfig
from vxl.system import System


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


def test_station_config_load_requires_station_yaml(voxel_home: Path) -> None:
    del voxel_home
    with pytest.raises(StationNotConfiguredError, match="vxl station init"):
        StationConfig.load()


def test_station_config_initialize_promotes_system_config_and_preserves_file_identity(
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

    StationConfig.initialize("scope-a", station_id=station_id)
    monkeypatch.setenv("VOXEL_NAME", "ambient-name")
    monkeypatch.setenv("VOXEL_STORE", "/env-store")
    loaded = StationConfig.load()

    assert loaded.info.model_dump(mode="json") == {"id": str(station_id), "name": "scope-a"}
    assert loaded.store == Path("/env-store")
    assert loaded.scratch == Path("/node-scratch")
    assert loaded.max_ram_fraction == 0.6
    assert (home / "system.yaml").is_file()
    assert (home / "station.yaml").is_file()

    with pytest.raises(FileExistsError, match="already configured"):
        StationConfig.initialize("scope-b")


def test_station_file_gives_the_metadata_forms(voxel_home: Path) -> None:
    voxel_home.mkdir()
    station = voxel_home / "station.yaml"
    head = "schema_version: 1\nid: 12345678-1234-5678-1234-567812345678\nname: scope\n"

    station.write_text(head, encoding="utf-8")
    assert StationConfig.load().metadata_menu() == {"Base": "vxl.core.instrument.metadata.ExperimentMetadata"}

    station.write_text(head + "metadata_schemas:\n  exaspim: vxl_drivers.metadata.ExaspimMetadata\n", encoding="utf-8")
    assert StationConfig.load().metadata_menu() == {
        "Base": "vxl.core.instrument.metadata.ExperimentMetadata",
        "exaspim": "vxl_drivers.metadata.ExaspimMetadata",
    }

    station.write_text(head + "metadata_schemas:\n  lab: vxl.system.System\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"'lab': vxl\.system\.System is not an ExperimentMetadata subclass"):
        StationConfig.load()
