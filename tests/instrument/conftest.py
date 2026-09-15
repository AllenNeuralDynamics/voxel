from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from vxl_records import SQLiteRecords

from vxl._utils.files import load_yaml
from vxl.instrument import Instrument, InstrumentConfig, InstrumentStore
from vxl.system import System


@pytest.fixture
def instrument_template() -> Path:
    return Path(__file__).parents[2] / "src/vxl/station/templates/builtins/simulated-local.voxel.yaml"


@pytest.fixture
def instrument_config(instrument_template: Path, request: pytest.FixtureRequest) -> InstrumentConfig:
    config = load_yaml(instrument_template, InstrumentConfig).model_dump()
    config["hal"]["devices"]["camera_1"]["init"]["frame_source"]["sensor_size_px"] = "64,64"
    if routing_type := getattr(request, "param", None):
        dimension = config["hal"]["optical_routing"]["excitation_side"]
        dimension["type"] = routing_type
        dimension["routes"] = {"lower": dimension["routes"]["left"], "upper": dimension["routes"]["right"]}
        config["default"]["routing"]["excitation_side"] = {"threshold": 5}
    return InstrumentConfig.model_validate(config)


@pytest.fixture
def system(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> System:
    monkeypatch.setattr(System, "config_path", classmethod(lambda _cls: tmp_path / "system.yaml"))
    return System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)


@pytest.fixture
def records(tmp_path: Path) -> SQLiteRecords:
    return SQLiteRecords(
        tmp_path / "records.sqlite3",
        resolve_root=lambda spec: tmp_path / "data" / spec.path.as_posix(),
    )


@pytest.fixture
def instrument_store(tmp_path: Path, instrument_config: InstrumentConfig) -> InstrumentStore:
    home = InstrumentStore.instantiate(instrument_config, "test", tmp_path)
    return InstrumentStore.load(home)


@pytest.fixture
async def instrument(
    instrument_store: InstrumentStore, records: SQLiteRecords, system: System
) -> AsyncIterator[Instrument]:
    instrument = Instrument(instrument_store, records=records, system=system)
    try:
        yield instrument
    finally:
        try:
            await instrument.stop_acquisition()
        finally:
            await instrument.close()


@pytest.fixture
async def opened_instrument(instrument: Instrument) -> Instrument:
    await instrument.open()
    return instrument
