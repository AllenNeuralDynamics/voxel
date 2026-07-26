import asyncio

import pytest
from vxlib.quantity import Frequency, Time

from vxl.daq.clocked import Signals
from vxl.instrument import AcquisitionMode, Instrument
from vxlib import Cell


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
        RuntimeError,
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
        RuntimeError,
        match="Unable to update synchronized outputs: requires mode idle; current mode is preview",
    ):
        await instrument.update_signals("generator", signals)
