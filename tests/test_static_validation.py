from pathlib import Path

import pytest
from pydantic import ValidationError

from vxl.app import VoxelApp
from vxl.camera import SensorROI
from vxl.daq.clocked import Signals
from vxl.daq.clocked.waveform import validate_waveform
from vxl.errors import Invalid, Loaded, Missing, OperationRejectedError, StartupError
from vxl.instrument import Instrument
from vxl.instrument.bench import InstrumentBench, InstrumentConfig, InstrumentInspection
from vxl.instrument.state import AcquisitionTask, InstrumentState
from vxl.instrument.topology import HALConfig
from vxlib import Cell, load_yaml

TEMPLATE = Path(__file__).parents[1] / "src/vxl/_templates/simulated-local.voxel.yaml"


def _config() -> InstrumentConfig:
    return load_yaml(TEMPLATE, InstrumentConfig)


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


def test_check_config_returns_the_parsed_config() -> None:
    checked = InstrumentBench.check_config(TEMPLATE)

    assert checked.ok
    assert isinstance(checked.config, Loaded)
    assert checked.config.value == _config()
    assert isinstance(checked.state, Missing)
    assert checked.violations == ()


def test_check_config_reports_unknown_top_level_field(tmp_path: Path) -> None:
    path = tmp_path / "typo.voxel.yaml"
    path.write_text(f"{TEMPLATE.read_text(encoding='utf-8')}\nmisspelled: true\n", encoding="utf-8")

    checked = InstrumentBench.check_config(path)

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


def test_bench_check_collects_config_and_state_errors(tmp_path: Path) -> None:
    directory = tmp_path / "broken.voxel"
    directory.mkdir()
    (directory / "config.yaml").write_text("hal: []\n", encoding="utf-8")
    (directory / "bench.json").write_text("{", encoding="utf-8")

    inspected = InstrumentBench.check(directory)

    assert isinstance(inspected.config, Invalid)
    assert isinstance(inspected.state, Invalid)
    assert not inspected.ok
    assert {violation.loc[0] for violation in inspected.violations} == {"config", "bench"}


def test_inspection_requires_violations_for_blocking_artifact_statuses() -> None:
    with pytest.raises(ValidationError, match="missing or invalid config must include a config violation"):
        InstrumentInspection(config=Missing())

    with pytest.raises(ValidationError, match="invalid state must include a bench violation"):
        InstrumentInspection(config=Loaded(value=_config()), state=Invalid())


def test_discovery_keeps_file_errors_distinct_from_model_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "missing-config.voxel"
    directory.mkdir()
    monkeypatch.setattr(VoxelApp, "instruments_dir", property(lambda _app: tmp_path))

    info = object.__new__(VoxelApp).discover().instruments["missing-config"]

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
    directory = tmp_path / "broken-stage.voxel"
    directory.mkdir()
    config = TEMPLATE.read_text(encoding="utf-8").replace("    x: x_axis\n", "    x: missing_axis\n", 1)
    (directory / "config.yaml").write_text(config, encoding="utf-8")
    monkeypatch.setattr(VoxelApp, "instruments_dir", property(lambda _app: tmp_path))

    info = object.__new__(VoxelApp).discover().instruments["broken-stage"]

    assert isinstance(info.config, Loaded)
    assert isinstance(info.state, Missing)
    assert [(violation.code, violation.loc, violation.msg) for violation in info.violations] == [
        (
            "hal.stage.device_missing",
            ("config", "hal", "stage", "x"),
            "Stage axis 'x' references missing device 'missing_axis'.",
        )
    ]
    payload = info.model_dump(mode="json")
    assert payload["config"]["status"] == "loaded"
    assert payload["state"] == {"status": "missing"}
    assert payload["violations"][0]["loc"][0] == "config"


def test_check_config_collects_independent_semantic_violations(tmp_path: Path) -> None:
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

    checked = InstrumentBench.check_config(path)

    assert isinstance(checked.config, Loaded)
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


def test_bench_uses_config_default_only_when_file_is_missing(tmp_path: Path) -> None:
    config = _config()
    directory = config.instantiate("missing-bench", tmp_path)
    inspection = InstrumentBench.check(directory)

    bench = InstrumentBench.load(directory)

    assert isinstance(inspection.config, Loaded)
    assert isinstance(inspection.state, Missing)
    assert inspection.ok
    assert bench.value.imaging == config.default.imaging
    assert bench.home == directory
    assert bench.config == InstrumentConfig.read(directory / "config.yaml")
    assert not (directory / "bench.json").exists()


async def test_bench_saves_selected_live_fields_as_defaults(tmp_path: Path) -> None:
    config = _config()
    directory = config.instantiate("save-default", tmp_path)
    bench = InstrumentBench.load(directory)
    stencil = bench.value.stencil.model_copy(update={"x_offset": 42.0})
    await bench.update(stencil=stencil)

    await bench.save_as_default({"stencil"})

    assert bench.default.value.stencil == stencil
    assert bench.config.default.stencil == stencil
    assert InstrumentConfig.read(directory / "config.yaml").default.stencil == stencil


async def test_bench_restores_selected_defaults_to_live_state(tmp_path: Path) -> None:
    config = _config()
    directory = config.instantiate("restore-default", tmp_path)
    bench = InstrumentBench.load(directory)
    await bench.update(stencil=bench.value.stencil.model_copy(update={"x_offset": 42.0}))

    await bench.restore_default({"stencil"})

    assert bench.value.stencil == bench.default.value.stencil
    persisted = InstrumentState.model_validate_json((directory / "bench.json").read_text(encoding="utf-8"))
    assert persisted.stencil == bench.default.value.stencil


def test_instrument_constructs_from_the_validated_snapshot_without_rereading(tmp_path: Path) -> None:
    config = _config()
    directory = config.instantiate("validated", tmp_path)
    bench = InstrumentBench.load(directory)
    (directory / "config.yaml").write_text("hal: []\n", encoding="utf-8")

    instrument = Instrument(bench)

    assert instrument.path == directory
    assert instrument.default.value == config.default
    assert instrument.state.value == bench.value


def test_bench_rejects_an_invalid_existing_file(tmp_path: Path) -> None:
    directory = _config().instantiate("invalid-bench", tmp_path)
    path = directory / "bench.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(StartupError) as raised:
        InstrumentBench.load(directory)

    assert {violation.code for violation in raised.value.violations} == {"bench.load"}
    assert path.read_text(encoding="utf-8") == "{"


def test_bench_rejects_an_incompatible_existing_file(tmp_path: Path) -> None:
    config = _config()
    directory = config.instantiate("incompatible-bench", tmp_path)
    path = directory / "bench.json"
    path.write_text(_incompatible_state(config).model_dump_json(), encoding="utf-8")

    with pytest.raises(StartupError) as raised:
        InstrumentBench.load(directory)

    assert {violation.code for violation in raised.value.violations} == {"imaging.channel.detection_missing"}
    assert "missing_camera" in str(raised.value)


def test_archive_bench_uses_the_next_available_backup_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(VoxelApp, "instruments_dir", property(lambda _app: tmp_path))
    app = object.__new__(VoxelApp)
    app._active = Cell(None)
    directory = tmp_path / "scope.voxel"
    directory.mkdir()
    bench = directory / "bench.json"

    bench.write_text("first", encoding="utf-8")
    first = app.archive_bench("scope")
    bench.write_text("second", encoding="utf-8")
    second = app.archive_bench("scope")

    assert first.name == "bench.bak.json"
    assert first.read_text(encoding="utf-8") == "first"
    assert second.name == "bench.bak.2.json"
    assert second.read_text(encoding="utf-8") == "second"
    assert not bench.exists()


def test_bench_check_reports_hal_incompatibility(tmp_path: Path) -> None:
    config = _config()
    directory = config.instantiate("incompatible", tmp_path)
    (directory / "bench.json").write_text(_incompatible_state(config).model_dump_json(), encoding="utf-8")

    checked = InstrumentBench.check(directory)

    assert isinstance(checked.config, Loaded)
    assert isinstance(checked.state, Loaded)
    assert [(violation.code, violation.loc, violation.msg) for violation in checked.violations] == [
        (
            "imaging.channel.detection_missing",
            ("bench", "imaging", "channels", "gfp", "detection"),
            "Detection assembly 'missing_camera' is not configured.",
        )
    ]


def test_bench_check_collects_independent_state_semantic_violations(tmp_path: Path) -> None:
    config = _config()
    directory = config.instantiate("semantic-state", tmp_path)
    (directory / "bench.json").write_text(
        _semantically_invalid_state(config).model_dump_json(),
        encoding="utf-8",
    )

    checked = InstrumentBench.check(directory)

    assert isinstance(checked.state, Loaded)
    assert [(violation.code, violation.loc) for violation in checked.violations] == [
        (
            "imaging.profile.channel_missing",
            ("bench", "imaging", "profiles", "single_gfp", "channels", 0),
        ),
        ("task.profile_missing", ("bench", "tasks", "broken", "profile_ids", 0)),
    ]


async def test_bench_rejects_semantically_invalid_update_without_persisting(tmp_path: Path) -> None:
    config = _config()
    directory = config.instantiate("semantic-update", tmp_path)
    bench = InstrumentBench.load(directory)
    original = bench.value

    with pytest.raises(OperationRejectedError, match=r"missing_channel.*missing_profile"):
        await bench.set(_semantically_invalid_state(config))

    assert bench.value == original
    assert not (directory / "bench.json").exists()


def test_discovery_preserves_static_bench_violations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    directory = config.instantiate("incompatible", tmp_path)
    (directory / "bench.json").write_text(
        _incompatible_state(config).model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr(VoxelApp, "instruments_dir", property(lambda _app: tmp_path))

    info = object.__new__(VoxelApp).discover().instruments["incompatible"]

    assert isinstance(info.config, Loaded)
    assert isinstance(info.config.value, InstrumentConfig)
    assert isinstance(info.state, Loaded)
    assert isinstance(info.state.value, InstrumentState)
    assert [(violation.code, violation.loc, violation.msg) for violation in info.violations] == [
        (
            "imaging.channel.detection_missing",
            ("bench", "imaging", "channels", "gfp", "detection"),
            "Detection assembly 'missing_camera' is not configured.",
        )
    ]


async def test_launch_rejects_static_violations_before_constructing_instrument(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(VoxelApp, "instruments_dir", property(lambda _app: tmp_path))
    app = object.__new__(VoxelApp)
    app._active = Cell(None)
    directory = tmp_path / "broken.voxel"
    directory.mkdir()
    (directory / "config.yaml").write_text("hal: []\n", encoding="utf-8")
    (directory / "bench.json").write_text("{", encoding="utf-8")

    def unexpected_instrument(_instrument: Instrument, _bench: object) -> None:
        raise AssertionError("Instrument construction must not run after static validation fails")

    monkeypatch.setattr(Instrument, "__init__", unexpected_instrument)

    with pytest.raises(StartupError) as raised:
        await app.launch("broken")

    assert {violation.loc[0] for violation in raised.value.violations} == {"config", "bench"}
    assert app.active.value is None
