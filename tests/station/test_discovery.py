from pathlib import Path

import pytest

from vxl.instrument import Instrument
from vxl.instrument.config import InstrumentConfig, InstrumentState
from vxl.instrument.errors import StartupError
from vxl.instrument.store import InstrumentStore, Invalid, Loaded, Missing
from vxl.station import Station, StationStatus


def _incompatible_state(config: InstrumentConfig) -> InstrumentState:
    state = InstrumentState(**config.default.model_dump())
    channel = state.imaging.channels["gfp"].model_copy(update={"detection": "missing_camera"})
    channels = {**state.imaging.channels, "gfp": channel}
    imaging = state.imaging.model_copy(update={"channels": channels})
    return state.model_copy(update={"imaging": imaging})


def test_discovery_keeps_file_errors_distinct_from_model_errors(
    station: Station,
) -> None:
    directory = station.instruments_dir / "missing-config.voxel"
    directory.mkdir()

    info = station.discover_instruments()["missing-config"]

    assert isinstance(info.config, Missing)
    assert isinstance(info.state, Missing)
    assert [(violation.code, violation.loc, violation.msg) for violation in info.violations] == [
        (
            "config.missing",
            ("config",),
            f"No InstrumentConfig found at {directory / 'config.yaml'}",
        )
    ]


def test_discovery_reports_an_unknown_stage_device(station: Station, instrument_template: Path) -> None:
    directory = station.instruments_dir / "broken-stage.voxel"
    directory.mkdir()
    config = instrument_template.read_text(encoding="utf-8").replace("    x: x_axis\n", "    x: missing_axis\n", 1)
    (directory / "config.yaml").write_text(config, encoding="utf-8")

    info = station.discover_instruments()["broken-stage"]

    assert isinstance(info.config, Invalid)
    assert isinstance(info.state, Missing)
    assert [(violation.code, violation.loc, violation.msg) for violation in info.violations] == [
        (
            "hal.stage.device_missing",
            ("config", "hal", "stage", "x"),
            "Stage axis 'x' references missing device 'missing_axis'.",
        )
    ]
    payload = info.model_dump(mode="json")
    assert payload["config"]["status"] == "invalid"
    assert payload["state"] == {"status": "missing"}
    assert payload["violations"][0]["loc"][0] == "config"


async def test_archive_state_uses_the_next_available_backup_name(
    station: Station,
) -> None:
    directory = station.instruments_dir / "scope.voxel"
    directory.mkdir()
    state_path = directory / "state.json"

    state_path.write_text("first", encoding="utf-8")
    first = await station.archive_state("scope")
    state_path.write_text("second", encoding="utf-8")
    second = await station.archive_state("scope")

    assert first.name == "state.bak.json"
    assert first.read_text(encoding="utf-8") == "first"
    assert second.name == "state.bak.2.json"
    assert second.read_text(encoding="utf-8") == "second"
    assert not state_path.exists()


def test_discovery_preserves_static_state_violations(
    station: Station,
    instrument_config: InstrumentConfig,
) -> None:
    config = instrument_config
    directory = InstrumentStore.instantiate(config, "incompatible", station.instruments_dir)
    (directory / "state.json").write_text(
        _incompatible_state(config).model_dump_json(),
        encoding="utf-8",
    )

    info = station.discover_instruments()["incompatible"]

    assert isinstance(info.config, Loaded)
    assert isinstance(info.config.value, InstrumentConfig)
    assert isinstance(info.state, Invalid)
    assert isinstance(info.state.value, InstrumentState)
    assert [(violation.code, violation.loc, violation.msg) for violation in info.violations] == [
        (
            "imaging.channel.detection_missing",
            ("state", "imaging", "channels", "gfp", "detection"),
            "Detection assembly 'missing_camera' is not configured.",
        )
    ]


async def test_launch_rejects_static_violations_before_constructing_instrument(
    station: Station,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = station.instruments_dir / "broken.voxel"
    directory.mkdir()
    (directory / "config.yaml").write_text("hal: []\n", encoding="utf-8")
    (directory / "state.json").write_text("{", encoding="utf-8")

    def unexpected_instrument(_instrument: Instrument, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("Instrument construction must not run after static validation fails")

    monkeypatch.setattr(Instrument, "__init__", unexpected_instrument)

    with pytest.raises(StartupError) as raised:
        await station.open_session("broken")

    assert {violation.loc[0] for violation in raised.value.violations} == {"config", "state"}
    assert station.state.value.status is StationStatus.IDLE
    assert station.state.value.session is None
