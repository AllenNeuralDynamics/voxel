from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from vxl_records import SQLiteRecords

from vxl import system as system_module
from vxl._utils.files import load_yaml
from vxl.devices.camera import SensorROI
from vxl.devices.daq.clocked import Signals
from vxl.devices.daq.clocked.waveform import validate_waveform
from vxl.instrument import Instrument
from vxl.instrument.config import AcquisitionTask, InstrumentConfig, InstrumentState
from vxl.instrument.errors import OperationRejectedError, StartupError
from vxl.instrument.store import InstrumentInspection, InstrumentStore, Invalid, Loaded, Missing
from vxl.instrument.topology import HALConfig
from vxl.station import Station, StationStatus
from vxl.system import StationConfig

TEMPLATE = Path(__file__).parents[1] / "src/vxl/station/templates/builtins/simulated-local.voxel.yaml"


def _config() -> InstrumentConfig:
    return load_yaml(TEMPLATE, InstrumentConfig)


def _station(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Station:
    monkeypatch.setattr(system_module, "_voxel_home", lambda: tmp_path / ".voxel")
    return Station(
        StationConfig(
            id=UUID("12345678-1234-5678-1234-567812345678"),
            name="scope",
        )
    )


def _incompatible_state(config: InstrumentConfig) -> InstrumentState:
    state = InstrumentState(**config.default.model_dump())
    channel = state.imaging.channels["gfp"].model_copy(update={"detection": "missing_camera"})
    channels = {**state.imaging.channels, "gfp": channel}
    imaging = state.imaging.model_copy(update={"channels": channels})
    return state.model_copy(update={"imaging": imaging})


def _semantically_invalid_state(config: InstrumentConfig) -> InstrumentState:
    state = InstrumentState(**config.default.model_dump())
    profile = state.imaging.profiles["single_gfp"].model_copy(update={"channels": ["missing_channel"]})
    profiles = {**state.imaging.profiles, "single_gfp": profile}
    imaging = state.imaging.model_copy(update={"profiles": profiles})
    task = AcquisitionTask(x=0, y=0, start=0, end=0, profile_ids=["missing_profile"])
    return state.model_copy(update={"imaging": imaging, "tasks": {"broken": task}})


def test_load_config_returns_the_parsed_config() -> None:
    checked = InstrumentStore.load_config(TEMPLATE)

    assert checked.ok
    assert isinstance(checked.config, Loaded)
    assert checked.config.value == _config()
    assert isinstance(checked.state, Missing)
    assert checked.violations == ()


def test_load_config_reports_unknown_top_level_field(tmp_path: Path) -> None:
    path = tmp_path / "typo.voxel.yaml"
    path.write_text(f"{TEMPLATE.read_text(encoding='utf-8')}\nmisspelled: true\n", encoding="utf-8")

    checked = InstrumentStore.load_config(path)

    assert isinstance(checked.config, Invalid)
    assert [(violation.code, violation.loc) for violation in checked.violations] == [
        ("config.extra_forbidden", ("config", "misspelled"))
    ]


def test_persisted_state_leaves_reject_unknown_fields() -> None:
    config = _config()
    profile = next(iter(config.default.imaging.profiles.values()))
    signals = next(iter(profile.sync.values()))
    waveform = next(iter(signals.waveforms.values()))

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Signals.model_validate({**signals.model_dump(), "sample_rae": signals.sample_rate})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_waveform({**waveform.model_dump(), "rest_voltge": 0})

    waveform_data = waveform.model_dump()
    waveform_data["voltage"] = {**waveform_data["voltage"], "minimum": 0}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_waveform(waveform_data)

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SensorROI.model_validate({"x": 0, "y": 0, "w": 128, "h": 128, "width": 128})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HALConfig.model_validate({**config.hal.model_dump(), "stgae": config.hal.stage})


def test_store_check_collects_config_and_state_errors(tmp_path: Path) -> None:
    directory = tmp_path / "broken.voxel"
    directory.mkdir()
    (directory / "config.yaml").write_text("hal: []\n", encoding="utf-8")
    (directory / "state.json").write_text("{", encoding="utf-8")

    inspected = InstrumentStore.check(directory)

    assert isinstance(inspected.config, Invalid)
    assert isinstance(inspected.state, Invalid)
    assert not inspected.ok
    assert {violation.loc[0] for violation in inspected.violations} == {"config", "state"}


def test_inspection_requires_violations_for_blocking_artifact_statuses() -> None:
    with pytest.raises(ValidationError, match="missing or invalid config must include a config violation"):
        InstrumentInspection(config=Missing())

    with pytest.raises(ValidationError, match="invalid state must include a state violation"):
        InstrumentInspection(config=Loaded(value=_config()), state=Invalid())


def test_discovery_keeps_file_errors_distinct_from_model_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    station = _station(tmp_path, monkeypatch)
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


def test_discovery_reports_an_unknown_stage_device(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    station = _station(tmp_path, monkeypatch)
    directory = station.instruments_dir / "broken-stage.voxel"
    directory.mkdir()
    config = TEMPLATE.read_text(encoding="utf-8").replace("    x: x_axis\n", "    x: missing_axis\n", 1)
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


def test_load_config_collects_independent_semantic_violations(tmp_path: Path) -> None:
    path = tmp_path / "semantic-errors.voxel.yaml"
    config = TEMPLATE.read_text(encoding="utf-8")
    config = config.replace("    x: x_axis\n", "    x: missing_axis\n", 1)
    config = config.replace(
        "    camera_1:\n      filter_wheels:",
        "    camera_1:\n      aux_devices: [missing_detection_aux]\n      filter_wheels:",
        1,
    )
    config = config.replace(
        "    laser_561:\n      routing:",
        "    laser_561:\n      aux_devices: [missing_aux]\n      routing:",
        1,
    )
    config = config.replace("illumination: laser_488", "illumination: missing_illumination", 1)
    path.write_text(config, encoding="utf-8")

    checked = InstrumentStore.load_config(path)

    assert isinstance(checked.config, Invalid)
    assert not checked.ok
    assert [(violation.code, violation.loc) for violation in checked.violations] == [
        ("hal.stage.device_missing", ("config", "hal", "stage", "x")),
        (
            "hal.detection.aux_device_missing",
            ("config", "hal", "detection", "camera_1", "aux_devices", 0),
        ),
        (
            "hal.illumination.aux_device_missing",
            ("config", "hal", "illumination", "laser_561", "aux_devices", 0),
        ),
        (
            "imaging.channel.illumination_missing",
            ("config", "default", "imaging", "channels", "gfp", "illumination"),
        ),
    ]


def test_store_uses_config_default_only_when_state_file_is_missing(tmp_path: Path) -> None:
    config = _config()
    directory = InstrumentStore.instantiate(config, "missing-state", tmp_path)
    inspection = InstrumentStore.check(directory)

    store = InstrumentStore.load(directory)

    assert isinstance(inspection.config, Loaded)
    assert isinstance(inspection.state, Missing)
    assert inspection.ok
    assert store.value.imaging == config.default.imaging
    assert store.home == directory
    assert store.config == load_yaml(directory / "config.yaml", InstrumentConfig)
    assert not (directory / "state.json").exists()


async def test_store_saves_selected_live_fields_as_defaults(tmp_path: Path) -> None:
    config = _config()
    directory = InstrumentStore.instantiate(config, "save-default", tmp_path)
    store = InstrumentStore.load(directory)
    stencil = store.value.stencil.model_copy(update={"x_offset": 42.0})
    await store.update(stencil=stencil)

    await store.save_as_default({"stencil"})

    assert store.default.value.stencil == stencil
    assert store.config.default.stencil == stencil
    assert load_yaml(directory / "config.yaml", InstrumentConfig).default.stencil == stencil


async def test_store_restores_selected_defaults_to_live_state(tmp_path: Path) -> None:
    config = _config()
    directory = InstrumentStore.instantiate(config, "restore-default", tmp_path)
    store = InstrumentStore.load(directory)
    await store.update(stencil=store.value.stencil.model_copy(update={"x_offset": 42.0}))

    await store.restore_default({"stencil"})

    assert store.value.stencil == store.default.value.stencil
    persisted = InstrumentState.model_validate_json((directory / "state.json").read_text(encoding="utf-8"))
    assert persisted.stencil == store.default.value.stencil


def test_instrument_constructs_from_the_validated_snapshot_without_rereading(tmp_path: Path) -> None:
    config = _config()
    directory = InstrumentStore.instantiate(config, "validated", tmp_path)
    store = InstrumentStore.load(directory)
    (directory / "config.yaml").write_text("hal: []\n", encoding="utf-8")

    instrument = Instrument(
        store,
        records=SQLiteRecords(
            tmp_path / "records.sqlite3",
            resolve_root=lambda _spec: tmp_path / "acquisitions",
        ),
    )

    assert instrument.path == directory
    assert instrument.default.value == config.default
    assert instrument.state.value == store.value


def test_store_rejects_an_invalid_existing_state_file(tmp_path: Path) -> None:
    directory = InstrumentStore.instantiate(_config(), "invalid-state", tmp_path)
    path = directory / "state.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(StartupError) as raised:
        InstrumentStore.load(directory)

    assert {violation.code for violation in raised.value.violations} == {"state.load"}
    assert path.read_text(encoding="utf-8") == "{"


def test_store_rejects_an_incompatible_existing_state_file(tmp_path: Path) -> None:
    config = _config()
    directory = InstrumentStore.instantiate(config, "incompatible-state", tmp_path)
    path = directory / "state.json"
    path.write_text(_incompatible_state(config).model_dump_json(), encoding="utf-8")

    with pytest.raises(StartupError) as raised:
        InstrumentStore.load(directory)

    assert {violation.code for violation in raised.value.violations} == {"imaging.channel.detection_missing"}
    assert "missing_camera" in str(raised.value)


async def test_archive_state_uses_the_next_available_backup_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    station = _station(tmp_path, monkeypatch)
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


def test_store_check_reports_hal_incompatibility(tmp_path: Path) -> None:
    config = _config()
    directory = InstrumentStore.instantiate(config, "incompatible", tmp_path)
    (directory / "state.json").write_text(_incompatible_state(config).model_dump_json(), encoding="utf-8")

    checked = InstrumentStore.check(directory)

    assert isinstance(checked.config, Loaded)
    assert isinstance(checked.state, Invalid)
    assert [(violation.code, violation.loc, violation.msg) for violation in checked.violations] == [
        (
            "imaging.channel.detection_missing",
            ("state", "imaging", "channels", "gfp", "detection"),
            "Detection assembly 'missing_camera' is not configured.",
        )
    ]


def test_store_check_collects_independent_state_semantic_violations(tmp_path: Path) -> None:
    config = _config()
    directory = InstrumentStore.instantiate(config, "semantic-state", tmp_path)
    (directory / "state.json").write_text(
        _semantically_invalid_state(config).model_dump_json(),
        encoding="utf-8",
    )

    checked = InstrumentStore.check(directory)

    assert isinstance(checked.state, Invalid)
    assert [(violation.code, violation.loc) for violation in checked.violations] == [
        (
            "imaging.profile.channel_missing",
            ("state", "imaging", "profiles", "single_gfp", "channels", 0),
        ),
        ("task.profile_missing", ("state", "tasks", "broken", "profile_ids", 0)),
    ]


async def test_store_rejects_semantically_invalid_update_without_persisting(tmp_path: Path) -> None:
    config = _config()
    directory = InstrumentStore.instantiate(config, "semantic-update", tmp_path)
    store = InstrumentStore.load(directory)
    original = store.value

    with pytest.raises(OperationRejectedError, match=r"missing_channel.*missing_profile"):
        await store.set(_semantically_invalid_state(config))

    assert store.value == original
    assert not (directory / "state.json").exists()


def test_discovery_preserves_static_state_violations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    station = _station(tmp_path, monkeypatch)
    config = _config()
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    station = _station(tmp_path, monkeypatch)
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
