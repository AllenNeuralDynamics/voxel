import asyncio
from pathlib import PurePosixPath
from types import SimpleNamespace
from typing import Any, cast

import pytest
from vxl_records import StorageSpec
from vxlib.quantity import Frequency, Time
from vxlib.reactivity import Cell

from vxl.devices.daq.clocked import Signals
from vxl.instrument import AcquisitionMode, Instrument
from vxl.instrument.config import WriterPatch
from vxl.instrument.core import AcquisitionRequest
from vxl.instrument.errors import InstrumentBusyError, OperationRejectedError


def instrument_in_mode(mode: AcquisitionMode) -> Instrument:
    instrument = object.__new__(Instrument)
    instrument._mode = Cell(mode)
    return instrument


@pytest.mark.parametrize("mode", [AcquisitionMode.IDLE, AcquisitionMode.PREVIEW])
def test_ensure_mode_accepts_any_allowed_mode(mode: AcquisitionMode) -> None:
    instrument = instrument_in_mode(mode)

    instrument._ensure_mode(
        "update tasks",
        AcquisitionMode.IDLE,
        AcquisitionMode.PREVIEW,
    )


def test_ensure_mode_reports_operation_allowed_modes_and_current_mode() -> None:
    instrument = instrument_in_mode(AcquisitionMode.CAPTURE)

    with pytest.raises(
        InstrumentBusyError,
        match="Unable to update tasks: requires mode idle or preview; current mode is capture",
    ):
        instrument._ensure_mode(
            "update tasks",
            AcquisitionMode.IDLE,
            AcquisitionMode.PREVIEW,
        )


async def test_update_signals_requires_idle_mode() -> None:
    instrument = instrument_in_mode(AcquisitionMode.PREVIEW)
    instrument._lock = asyncio.Lock()
    signals = Signals(
        sample_rate=Frequency(1000),
        duration=Time(0.01),
        waveforms={},
    )

    with pytest.raises(
        InstrumentBusyError,
        match="Unable to update synchronized outputs: requires mode idle; current mode is preview",
    ):
        await instrument.update_signals("generator", signals)


async def test_edit_checks_mode_after_acquiring_instrument_lock() -> None:
    instrument = instrument_in_mode(AcquisitionMode.IDLE)
    instrument._lock = asyncio.Lock()
    await instrument._lock.acquire()
    edit = asyncio.create_task(instrument.update_output(WriterPatch()))
    await asyncio.sleep(0)

    await instrument._mode.set(AcquisitionMode.CAPTURE)
    instrument._lock.release()

    with pytest.raises(
        InstrumentBusyError,
        match="Unable to update output settings: requires mode idle or preview; current mode is capture",
    ):
        await edit


async def test_generic_device_mutations_reject_capture_mode() -> None:
    instrument = cast("Any", instrument_in_mode(AcquisitionMode.CAPTURE))
    instrument._lock = asyncio.Lock()
    instrument._hal = SimpleNamespace(devices={"camera": SimpleNamespace()})

    with pytest.raises(
        InstrumentBusyError,
        match="Unable to set device properties: requires mode idle or preview; current mode is capture",
    ):
        await instrument.set_device_properties("camera", {"exposure_time_ms": 10})

    with pytest.raises(
        InstrumentBusyError,
        match="Unable to execute a device command: requires mode idle or preview; current mode is capture",
    ):
        await instrument.execute_device_command("camera", "reset")

    with pytest.raises(
        InstrumentBusyError,
        match="Unable to move the stage: requires mode idle or preview; current mode is capture",
    ):
        await instrument.move_stage(x=1)


async def test_apply_settings_uses_locked_public_transition() -> None:
    instrument = cast("Any", instrument_in_mode(AcquisitionMode.IDLE))
    instrument._lock = asyncio.Lock()
    lock_was_held = False

    async def apply() -> None:
        nonlocal lock_was_held
        lock_was_held = instrument._lock.locked()

    instrument._apply_settings = apply

    await instrument.apply_settings()

    assert lock_was_held


async def test_acquisition_plans_after_acquiring_instrument_lock() -> None:
    instrument = cast("Any", instrument_in_mode(AcquisitionMode.IDLE))
    instrument._lock = asyncio.Lock()
    instrument._store = SimpleNamespace(value=object())
    planned = asyncio.Event()

    def generate_plan(_task_ids: list[str] | None) -> list[object]:
        planned.set()
        return []

    instrument._generate_plan = generate_plan
    request = AcquisitionRequest(storage=StorageSpec(path=PurePosixPath("run")))

    await instrument._lock.acquire()
    acquisition = asyncio.create_task(instrument.start_acquisition(request))
    await asyncio.sleep(0)

    assert not planned.is_set()
    instrument._lock.release()

    with pytest.raises(OperationRejectedError, match="No tasks planned"):
        await acquisition
    assert planned.is_set()
