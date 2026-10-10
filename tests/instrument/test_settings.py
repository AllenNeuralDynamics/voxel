import pytest

from vxl.devices.camera import SensorROI
from vxl.instrument import Instrument, InstrumentConfig, InstrumentState, InstrumentStore
from vxl.instrument.errors import SettingsPersistenceError, StartupError


@pytest.fixture
def instrument_config(instrument_config: InstrumentConfig) -> InstrumentConfig:
    config = instrument_config.model_dump()
    devices = config["hal"]["devices"]
    devices["camera_1"]["init"]["frame_source"]["sensor_size_px"] = "128,128"
    devices["camera_1"]["autosave"] = ["exposure_time_ms"]
    devices["laser_488"]["autosave"] = "*"
    devices["laser_561"]["autosave"] = "*"
    config["default"]["imaging"]["profiles"]["single_gfp"]["props"] = {"camera_1": {"binning": 2}}
    return InstrumentConfig.model_validate(config)


async def test_autosave_merges_accepted_values_and_ignores_other_writes(
    opened_instrument: Instrument, instrument_store: InstrumentStore
) -> None:
    instrument = opened_instrument
    result = await instrument.set_device_properties(
        "camera_1", {"exposure_time_ms": 12.3456, "binning": 1, "sensor_size_px": "64,64"}
    )
    assert not result.is_ok
    accepted = result.ok["exposure_time_ms"].value
    assert accepted != 12.3456
    assert instrument.active_profile.props["camera_1"] == {"binning": 2, "exposure_time_ms": accepted}

    result = await instrument.set_device_properties(
        "laser_488", {"source_power_setpoint_mw": 40, "output_level_percent": 25, "modulation_mode": "digital"}
    )
    assert not result.is_ok
    assert instrument.active_profile.props["laser_488"] == {
        "source_power_setpoint_mw": 40,
        "output_level_percent": 25,
    }
    saved = instrument_store.value
    (await instrument.set_device_properties("laser_561", {"output_level_percent": 10})).unwrap()
    camera = instrument.active_channels["gfp"].camera
    (await camera.props.set(exposure_time_ms=5)).unwrap()
    await camera.props.refresh()  # Observations do not save internal workflow writes.
    assert instrument_store.value == saved
    assert InstrumentStore.load(instrument_store.home).value == saved
    await instrument.apply_settings()
    assert (await camera.props.get("exposure_time_ms")).ok["exposure_time_ms"].value == accepted


async def test_roi_autosaves_applied_rectangle_and_explicit_full_frame(
    opened_instrument: Instrument, instrument_store: InstrumentStore
) -> None:
    instrument = opened_instrument
    requested = {"x": 0, "y": 0, "w": 81, "h": 81}
    result = await instrument.execute_device_command("camera_1", "update_roi", kwargs={"roi": requested})
    applied = SensorROI.model_validate(result.unwrap())
    assert applied.w != requested["w"]  # The camera snapped the requested size.
    assert instrument.active_profile.rois["camera_1"] == applied
    saved = instrument_store.value
    failed = await instrument.execute_device_command("camera_1", "update_roi", kwargs={"roi": requested, "snap": False})
    assert not failed.is_ok
    assert instrument_store.value == saved

    (await instrument.execute_device_command("camera_1", "reset_roi")).unwrap()
    full_frame = SensorROI(x=0, y=0, w=128, h=128)
    assert instrument.active_profile.rois["camera_1"] == full_frame
    restored = InstrumentStore.load(instrument_store.home)
    assert restored.value.imaging.profiles["single_gfp"].rois["camera_1"] == full_frame


async def test_save_failure_reports_hardware_change_without_committing_profile(
    opened_instrument: Instrument, instrument_store: InstrumentStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail_save(_state: InstrumentState) -> None:
        raise OSError("disk full")

    await opened_instrument.set_device_properties("camera_1", {"exposure_time_ms": 15})
    saved = instrument_store.value
    monkeypatch.setattr(instrument_store, "_save", fail_save)
    with pytest.raises(SettingsPersistenceError, match=r"accepted the change.*could not be saved.*disk full"):
        await opened_instrument.set_device_properties("camera_1", {"exposure_time_ms": 20})
    actual = await opened_instrument.get_device_properties("camera_1", ["exposure_time_ms"])
    assert actual.ok["exposure_time_ms"].value == 20
    assert instrument_store.value == saved
    assert InstrumentStore.load(instrument_store.home).value == saved


@pytest.mark.parametrize("property_name", ["missing", "sensor_size_px"])
async def test_explicit_autosave_policy_requires_writable_properties(
    instrument: Instrument, property_name: str
) -> None:
    instrument.hardware_config.devices["camera_1"].autosave = [property_name]
    with pytest.raises(StartupError) as caught:
        await instrument.open()
    assert [(v.code, v.loc) for v in caught.value.violations] == [
        ("device.autosave.not_writable", ("hal", "devices", "camera_1", "autosave", 0))
    ]
