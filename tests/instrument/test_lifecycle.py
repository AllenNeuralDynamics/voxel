import asyncio
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest
from vxl_records import SQLiteRecords, StorageSpec
from vxlib.reactivity import Cell

from rigup import CommandRequest, DeviceInterface, DeviceProps
from vxl.instrument import AcquisitionMode, Instrument, InstrumentConfig, InstrumentState, InstrumentStore
from vxl.instrument.config import AcquisitionTask, WriterPatch
from vxl.instrument.errors import InstrumentBusyError, OperationRejectedError, StartupError, Violation
from vxl.instrument.models import AcquisitionRequest
from vxl.system import System


def test_violation_serializes_for_api_responses() -> None:
    violation = Violation(
        code="build.import",
        msg="Device failed to import",
        loc=("hal", "devices", "camera"),
    )

    assert violation.model_dump(mode="json") == {
        "code": "build.import",
        "msg": "Device failed to import",
        "loc": ["hal", "devices", "camera"],
    }


def test_startup_error_formats_a_terminal_report() -> None:
    error = StartupError(
        [
            Violation(
                code="build.import",
                msg="Driver unavailable",
                loc=("hal", "devices", "camera"),
            ),
            Violation(msg="No usable stage"),
        ]
    )

    assert str(error) == (
        "Instrument startup failed:\n  - [build.import] hal.devices.camera: Driver unavailable\n  - No usable stage"
    )


def test_construction_uses_validated_snapshot_without_rereading(
    instrument_store: InstrumentStore, records: SQLiteRecords, system: System
) -> None:
    (instrument_store.home / "config.yaml").write_text("hal: []\n", encoding="utf-8")
    instrument = Instrument(instrument_store, records=records, system=system)
    assert instrument.path == instrument_store.home
    assert instrument.default.value == instrument_store.config.default
    assert instrument.state.value == instrument_store.value


@pytest.mark.parametrize("phase", ["channels", "validation"])
async def test_startup_failure_closes_open_hal(
    instrument: Instrument, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    def fail_channels():
        assert instrument._hal.devices
        raise RuntimeError("channel initialization failed")

    async def fail_validation():
        assert instrument._hal.devices
        return [Violation(code="test.startup", msg="instrument validation failed")]

    if phase == "channels":
        monkeypatch.setattr(instrument, "_build_channels", fail_channels)
        error, message = RuntimeError, "channel initialization failed"
    else:
        monkeypatch.setattr(instrument, "_startup_violations", fail_validation)
        error, message = StartupError, "instrument validation failed"

    with pytest.raises(error, match=message):
        await instrument.open()
    assert not instrument._hal.devices
    assert not instrument._hal.routing
    assert not instrument._device_unsubs


async def test_instrument_startup_collects_profile_port_and_stage_violations(
    instrument: Instrument,
    instrument_store: InstrumentStore,
    instrument_config: InstrumentConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = instrument_config
    state = InstrumentState(**config.default.model_dump())
    profile = state.imaging.profiles["single_gfp"]
    profile = profile.model_copy(
        update={
            "sync": {**profile.sync, "camera_1": profile.sync["daq"]},
            "props": {
                "camera_1": {"temperature": -20, "missing": 1},
                "unavailable": {"gain": 1},
            },
            "setup": {
                "camera_1": [CommandRequest(attr="missing_command")],
                "unavailable": [CommandRequest(attr="configure")],
            },
        }
    )
    imaging = state.imaging.model_copy(update={"profiles": {**state.imaging.profiles, "single_gfp": profile}})
    state = state.model_copy(
        update={
            "imaging": imaging,
            "tasks": {"outside": AcquisitionTask(x=101, y=50, start=-1, end=50, profile_ids=["single_gfp"])},
        }
    )
    camera_interface = DeviceInterface.model_validate(
        {
            "uid": "camera_1",
            "type": "camera",
            "commands": {},
            "properties": {
                "temperature": {
                    "name": "temperature",
                    "label": "Temperature",
                    "dtype": "float",
                    "access": "ro",
                }
            },
        }
    )
    daq_interface = DeviceInterface(uid="daq", type="signal_generator", commands={}, properties={})

    def axis():
        return SimpleNamespace(lower_limit=Cell(0), upper_limit=Cell(100))

    hal = SimpleNamespace(
        device_interfaces={"camera_1": camera_interface, "daq": daq_interface},
        signal_generators={"daq": SimpleNamespace(ports=Cell({"camera_1": "ao0", "aotf_1": "ao1"}))},
        stage=SimpleNamespace(x=axis(), y=axis(), z=axis()),
    )
    with monkeypatch.context() as patch:
        patch.setattr(instrument_store, "_value", state)
        patch.setattr(instrument, "_hal", hal)
        violations = await instrument._startup_violations()

    assert {violation.code for violation in violations} == {
        "state.stage_position.out_of_bounds",
        "imaging.profile.props.device_unavailable",
        "imaging.profile.props.property_missing",
        "imaging.profile.props.property_read_only",
        "imaging.profile.setup.command_missing",
        "imaging.profile.setup.device_unavailable",
        "imaging.profile.sync.not_signal_generator",
        "imaging.profile.sync.port_missing",
    }
    assert {violation.loc for violation in violations if violation.code == "state.stage_position.out_of_bounds"} == {
        ("state", "tasks", "outside", "x"),
        ("state", "tasks", "outside", "start"),
        ("state", "stencil", "z_end"),
    }


async def test_startup_exposes_device_properties_and_stage_updates(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    positions: list[float] = []
    arrived = asyncio.Event()

    def observe_position(update: tuple[str, DeviceProps]) -> None:
        device_id, props = update
        position = props.get("position")
        if device_id == "x_axis" and position is not None:
            value = float(position.value)
            positions.append(value)
            if value == 1:
                arrived.set()

    unsubscribe = instrument.device_props_updates.subscribe(observe_position)
    try:
        await instrument.move_stage(x=1, wait=True)
        await asyncio.wait_for(arrived.wait(), timeout=1)
        properties = await instrument.get_device_properties("x_axis", ["position"])
        assert properties["position"].unwrap().value == 1
        assert positions[-1] == 1
    finally:
        unsubscribe()


@pytest.mark.parametrize("mode", [AcquisitionMode.IDLE, AcquisitionMode.PREVIEW])
async def test_edits_accept_idle_and_preview(instrument: Instrument, mode: AcquisitionMode) -> None:
    await instrument._mode.set(mode)
    await instrument.update_metadata(notes="editable")
    assert instrument.state.value.metadata["notes"] == "editable"


async def test_edits_report_capture_restriction(instrument: Instrument) -> None:
    await instrument._mode.set(AcquisitionMode.CAPTURE)
    with pytest.raises(
        InstrumentBusyError, match="Unable to update tasks: requires mode idle or preview; current mode is capture"
    ):
        await instrument.update_tasks({})


async def test_update_signals_requires_idle_mode(instrument: Instrument) -> None:
    await instrument._mode.set(AcquisitionMode.PREVIEW)
    signals = instrument.active_profile.sync["daq"]
    with pytest.raises(
        InstrumentBusyError, match="Unable to update synchronized outputs: requires mode idle; current mode is preview"
    ):
        await instrument.update_signals("daq", signals)


async def test_edit_checks_mode_after_acquiring_lock(instrument: Instrument) -> None:
    async with instrument._lock:
        edit = asyncio.create_task(instrument.update_output(WriterPatch()))
        await asyncio.sleep(0)
        assert not edit.done()
        await instrument._mode.set(AcquisitionMode.CAPTURE)
    with pytest.raises(
        InstrumentBusyError,
        match="Unable to update output settings: requires mode idle or preview; current mode is capture",
    ):
        await edit


async def test_manual_device_mutations_reject_capture_mode(instrument: Instrument) -> None:
    await instrument._mode.set(AcquisitionMode.CAPTURE)
    with pytest.raises(InstrumentBusyError, match="Unable to set device properties"):
        await instrument.set_device_properties("camera_1", {"exposure_time_ms": 10})
    with pytest.raises(InstrumentBusyError, match="Unable to execute a device command"):
        await instrument.execute_device_command("camera_1", "reset")
    with pytest.raises(InstrumentBusyError, match="Unable to move the stage"):
        await instrument.move_stage(x=1)


async def test_apply_settings_uses_locked_public_transition(
    instrument: Instrument, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def apply() -> None:
        assert instrument._lock.locked()

    monkeypatch.setattr(instrument, "_apply_settings", apply)
    await instrument.apply_settings()


async def test_acquisition_plans_after_acquiring_lock(instrument: Instrument, monkeypatch: pytest.MonkeyPatch) -> None:
    planned = asyncio.Event()

    def generate_plan(_task_ids):
        planned.set()
        return []

    monkeypatch.setattr(instrument, "_generate_plan", generate_plan)
    request = AcquisitionRequest(storage=StorageSpec(path=PurePosixPath("run")))
    async with instrument._lock:
        acquisition = asyncio.create_task(instrument.start_acquisition(request))
        await asyncio.sleep(0)
        assert not planned.is_set()
    with pytest.raises(OperationRejectedError, match="No tasks planned"):
        await acquisition
    assert planned.is_set()
