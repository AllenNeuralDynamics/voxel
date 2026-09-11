import asyncio
from unittest.mock import AsyncMock, call

import pytest
from vxlib.history import Change, HistoryState, UndoHistory


async def test_replay_order_and_reactive_labels() -> None:
    history = UndoHistory()
    restore = AsyncMock()
    states: list[HistoryState] = []
    unsubscribe = history.state.subscribe(states.append)

    await history.record("First", Change(before=0, after=1), restore)
    await history.record("Second", Change(before=1, after=2), restore)
    await history.undo()
    await history.undo()
    await history.undo()
    await history.redo()
    await history.redo()
    await history.redo()

    assert restore.await_args_list == [call(1), call(0), call(1), call(2)]
    assert states == [
        HistoryState(undo_label="First"),
        HistoryState(undo_label="Second"),
        HistoryState(undo_label="First", redo_label="Second"),
        HistoryState(redo_label="First"),
        HistoryState(undo_label="First", redo_label="Second"),
        HistoryState(undo_label="Second"),
    ]
    unsubscribe()


async def test_noop_preserves_redo_but_new_edit_discards_it() -> None:
    history = UndoHistory()
    restore = AsyncMock()
    await history.record("First", Change(before=0, after=1), restore)
    await history.undo()
    await history.record("No change", Change(before=0, after=0), restore)
    assert history.state.value == HistoryState(redo_label="First")

    await history.record("Replacement", Change(before=0, after=2), restore)
    await history.redo()
    assert restore.await_args_list == [call(0)]
    assert history.state.value == HistoryState(undo_label="Replacement")
    await history.undo()
    assert restore.await_args_list == [call(0), call(0)]


async def test_gesture_merge_keeps_first_before_and_latest_after() -> None:
    history = UndoHistory()
    restore = AsyncMock()
    for value in range(1, 4):
        await history.record("Drag", Change(before=value - 1, after=value), restore, merge_key=("task", "drag-1"))

    await history.undo()
    assert history.state.value == HistoryState(redo_label="Drag")
    await history.redo()
    assert restore.await_args_list == [call(0), call(3)]


@pytest.mark.parametrize("middle_key", [None, ("task", "drag-2"), ("other-task", "drag-1")])
async def test_only_consecutive_matching_gestures_merge(middle_key) -> None:
    history = UndoHistory()
    restore = AsyncMock()
    key = ("task", "drag-1")
    await history.record("First", Change(before=0, after=1), restore, merge_key=key)
    await history.record("Middle", Change(before=1, after=2), restore, merge_key=middle_key)
    await history.record("Last", Change(before=2, after=3), restore, merge_key=key)

    for _ in range(3):
        await history.undo()
    assert restore.await_args_list == [call(2), call(1), call(0)]


async def test_replay_ends_a_merge_even_when_the_key_is_reused() -> None:
    history = UndoHistory()
    restore = AsyncMock()
    await history.record("Drag", Change(before=0, after=1), restore, merge_key="drag")
    await history.undo()
    await history.redo()
    await history.record("New edit", Change(before=1, after=2), restore, merge_key="drag")
    await history.undo()
    await history.undo()
    assert restore.await_args_list == [call(0), call(1), call(1), call(0)]


@pytest.mark.parametrize("operation", ["undo", "redo"])
@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_failed_replay_retains_entry_for_retry(operation, error) -> None:
    history = UndoHistory()
    restore = AsyncMock()
    await history.record("Edit", Change(before=0, after=1), restore)
    if operation == "redo":
        await history.undo()
    before = history.state.value
    restore.side_effect = error("restore failed")

    with pytest.raises(error, match="restore failed"):
        await getattr(history, operation)()
    assert history.state.value == before

    restore.side_effect = None
    await getattr(history, operation)()
    assert history.state.value == (
        HistoryState(redo_label="Edit") if operation == "undo" else HistoryState(undo_label="Edit")
    )


async def test_snapshots_are_copied_at_recording_and_each_replay() -> None:
    history = UndoHistory()
    before, after = ["before"], ["after"]
    restored: list[list[str]] = []

    async def restore(value: list[str]) -> None:
        restored.append(list(value))
        value.append("changed by restore")

    await history.record("Edit", Change(before=before, after=after), restore)
    before.append("changed by caller")
    after.append("changed by caller")
    await history.undo()
    await history.redo()
    await history.undo()
    assert restored == [["before"], ["after"], ["before"]]


async def test_capacity_evicts_oldest_edits_and_clear_discards_both_stacks() -> None:
    history = UndoHistory(capacity=2)
    restore = AsyncMock()
    for value in range(1, 4):
        await history.record(str(value), Change(before=value - 1, after=value), restore)
    await history.undo()
    await history.undo()
    await history.undo()
    assert restore.await_args_list == [call(2), call(1)]

    await history.redo()
    assert history.state.value == HistoryState(undo_label="2", redo_label="3")
    restore.reset_mock()
    await history.clear()
    await history.undo()
    await history.redo()
    restore.assert_not_awaited()
    assert history.state.value == HistoryState()


@pytest.mark.parametrize("capacity", [0, -1])
def test_capacity_must_be_positive(capacity: int) -> None:
    with pytest.raises(ValueError, match="capacity must be positive"):
        UndoHistory(capacity)
