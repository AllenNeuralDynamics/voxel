from pathlib import Path

import pytest
from pydantic import ValidationError

from vxl._utils.files import load_yaml
from vxl.instrument import InstrumentConfig, InstrumentState, InstrumentStore
from vxl.instrument.config import AcquisitionTask
from vxl.instrument.errors import OperationRejectedError, StartupError
from vxl.instrument.store import InstrumentInspection, Invalid, Loaded, Missing


def test_load_config_returns_the_parsed_config(instrument_template: Path) -> None:
    checked = InstrumentStore.load_config(instrument_template)

    assert checked.ok
    assert isinstance(checked.config, Loaded)
    assert checked.config.value == load_yaml(instrument_template, InstrumentConfig)
    assert isinstance(checked.state, Missing)
    assert checked.violations == ()


def test_load_config_reports_unknown_top_level_field(tmp_path: Path, instrument_template: Path) -> None:
    path = tmp_path / "typo.voxel.yaml"
    path.write_text(f"{instrument_template.read_text(encoding='utf-8')}\nmisspelled: true\n", encoding="utf-8")

    checked = InstrumentStore.load_config(path)

    assert isinstance(checked.config, Invalid)
    assert [(violation.code, violation.loc) for violation in checked.violations] == [
        ("config.extra_forbidden", ("config", "misspelled"))
    ]


def test_load_config_collects_independent_semantic_violations(tmp_path: Path, instrument_template: Path) -> None:
    path = tmp_path / "semantic-errors.voxel.yaml"
    config = instrument_template.read_text(encoding="utf-8")
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


def test_inspection_requires_violations_for_blocking_artifact_statuses(instrument_config: InstrumentConfig) -> None:
    with pytest.raises(ValidationError, match="missing or invalid config must include a config violation"):
        InstrumentInspection(config=Missing())

    with pytest.raises(ValidationError, match="invalid state must include a state violation"):
        InstrumentInspection(config=Loaded(value=instrument_config), state=Invalid())


def test_store_uses_config_default_only_when_state_file_is_missing(
    instrument_config: InstrumentConfig, tmp_path: Path
) -> None:
    config = instrument_config
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


async def test_store_saves_selected_live_fields_as_defaults(
    instrument_config: InstrumentConfig, tmp_path: Path
) -> None:
    config = instrument_config
    directory = InstrumentStore.instantiate(config, "save-default", tmp_path)
    store = InstrumentStore.load(directory)
    stencil = store.value.stencil.model_copy(update={"x_offset": 42.0})
    await store.update(stencil=stencil)

    await store.save_as_default({"stencil"})

    assert store.default.value.stencil == stencil
    assert store.config.default.stencil == stencil
    assert load_yaml(directory / "config.yaml", InstrumentConfig).default.stencil == stencil


async def test_store_restores_selected_defaults_to_live_state(
    instrument_config: InstrumentConfig, tmp_path: Path
) -> None:
    config = instrument_config
    directory = InstrumentStore.instantiate(config, "restore-default", tmp_path)
    store = InstrumentStore.load(directory)
    await store.update(stencil=store.value.stencil.model_copy(update={"x_offset": 42.0}))

    await store.restore_default({"stencil"})

    assert store.value.stencil == store.default.value.stencil
    persisted = InstrumentState.model_validate_json((directory / "state.json").read_text(encoding="utf-8"))
    assert persisted.stencil == store.default.value.stencil


def test_store_rejects_an_invalid_existing_state_file(instrument_config: InstrumentConfig, tmp_path: Path) -> None:
    directory = InstrumentStore.instantiate(instrument_config, "invalid-state", tmp_path)
    path = directory / "state.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(StartupError) as raised:
        InstrumentStore.load(directory)

    assert {violation.code for violation in raised.value.violations} == {"state.load"}
    assert path.read_text(encoding="utf-8") == "{"


def test_store_rejects_an_incompatible_existing_state_file(instrument_config: InstrumentConfig, tmp_path: Path) -> None:
    config = instrument_config
    directory = InstrumentStore.instantiate(config, "incompatible-state", tmp_path)
    path = directory / "state.json"
    path.write_text(_incompatible_state(config).model_dump_json(), encoding="utf-8")

    with pytest.raises(StartupError) as raised:
        InstrumentStore.load(directory)

    assert {violation.code for violation in raised.value.violations} == {"imaging.channel.detection_missing"}
    assert "missing_camera" in str(raised.value)


def test_store_check_reports_hal_incompatibility(instrument_config: InstrumentConfig, tmp_path: Path) -> None:
    config = instrument_config
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


def test_store_check_collects_independent_state_semantic_violations(
    instrument_config: InstrumentConfig, tmp_path: Path
) -> None:
    config = instrument_config
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


async def test_store_rejects_semantically_invalid_update_without_persisting(
    instrument_config: InstrumentConfig, tmp_path: Path
) -> None:
    config = instrument_config
    directory = InstrumentStore.instantiate(config, "semantic-update", tmp_path)
    store = InstrumentStore.load(directory)
    original = store.value

    with pytest.raises(OperationRejectedError, match=r"missing_channel.*missing_profile"):
        await store.set(_semantically_invalid_state(config))

    assert store.value == original
    assert not (directory / "state.json").exists()
