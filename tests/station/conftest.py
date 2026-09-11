from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import pytest

from vxl import system as system_module
from vxl._utils.files import load_yaml
from vxl.instrument import InstrumentConfig
from vxl.station import Station
from vxl.system import StationConfig


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


@pytest.fixture
def station_config(voxel_home: Path) -> StationConfig:
    del voxel_home
    return StationConfig(id=UUID("12345678-1234-5678-1234-567812345678"), name="scope")


@pytest.fixture
def instrument_template() -> Path:
    return Path(__file__).parents[2] / "src/vxl/station/templates/builtins/simulated-local.voxel.yaml"


@pytest.fixture
def instrument_config(instrument_template: Path) -> InstrumentConfig:
    return load_yaml(instrument_template, InstrumentConfig)


@pytest.fixture
async def station(station_config: StationConfig) -> AsyncIterator[Station]:
    station = Station(station_config)
    try:
        yield station
    finally:
        await station.close()
