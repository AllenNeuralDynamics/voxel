import asyncio

import pytest
from vxlib.history import HistoryState

from vxl.instrument import AcquisitionMode, Instrument, InstrumentStore
from vxl.instrument.config import InstrumentPreset, ProfilePatch
from vxl.instrument.errors import InstrumentBusyError, OperationRejectedError
from vxl.instrument.metadata import ExaspimMetadata


@pytest.mark.parametrize("boundary", ["close", "defaults", "preset", "metadata_schema"])
async def test_state_replacements_and_close_clear_both_stacks(instrument: Instrument, boundary: str) -> None:
    await instrument.update_metadata(notes="first")
    await instrument.update_metadata(notes="second")
    await instrument.undo()
    assert instrument.history.value.undo_label is not None
    assert instrument.history.value.redo_label is not None

    match boundary:
        case "close":
            await instrument.close()
        case "defaults":
            await instrument.restore_default({"output"})
        case "preset":
            await instrument.apply_preset(InstrumentPreset.from_state(instrument.state.value))
        case "metadata_schema":
            await instrument.set_metadata_schema(ExaspimMetadata)

    assert instrument.history.value == HistoryState()
    state = instrument.state.value
    await instrument.undo()
    await instrument.redo()
    assert instrument.state.value == state


async def test_rejected_replacement_preserves_history(instrument: Instrument) -> None:
    await instrument.update_metadata(notes="first")
    await instrument.update_metadata(notes="second")
    await instrument.undo()
    history = instrument.history.value
    state = instrument.state.value

    with pytest.raises(OperationRejectedError, match="Cannot restore non-default fields"):
        await instrument.restore_default({"unknown"})

    assert instrument.state.value == state
    assert instrument.history.value == history
    await instrument.redo()
    assert instrument.state.value.metadata["notes"] == "second"


@pytest.mark.parametrize("operation", ["undo", "redo"])
async def test_replay_checks_capture_mode_after_acquiring_lock(instrument: Instrument, operation: str) -> None:
    await instrument.update_metadata(notes="first")
    if operation == "redo":
        await instrument.undo()
    state = instrument.state.value
    history = instrument.history.value

    async with instrument._lock:
        replay = asyncio.create_task(getattr(instrument, operation)())
        await asyncio.sleep(0)
        assert not replay.done()
        await instrument._mode.set(AcquisitionMode.CAPTURE)

    try:
        with pytest.raises(InstrumentBusyError, match="current mode is capture"):
            await replay
        assert instrument.state.value == state
        assert instrument.history.value == history
    finally:
        await instrument._mode.set(AcquisitionMode.IDLE)

    await getattr(instrument, operation)()
    assert instrument.history.value != history


async def test_profile_edit_replays_against_original_profile_after_switch(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    original_id = instrument.active_profile_id.value
    other_id = next(uid for uid in instrument.state.value.imaging.profiles if uid != original_id)
    original = instrument.active_profile
    other = instrument.state.value.imaging.profiles[other_id]

    await instrument.update_profile(ProfilePatch(z_step=original.z_step * 2))
    await instrument.set_active_profile(other_id)
    await instrument.undo()
    assert instrument.active_profile_id.value == other_id
    assert instrument.state.value.imaging.profiles[original_id] == original
    assert instrument.active_profile == other

    await instrument.redo()
    assert instrument.active_profile_id.value == other_id
    assert instrument.active_profile == other
    persisted = InstrumentStore.load(instrument.path).value
    assert persisted.imaging.profiles[original_id].z_step == original.z_step * 2
    assert persisted.imaging.profiles[other_id] == other
