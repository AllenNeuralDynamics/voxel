import pytest

from vxl.instrument import Instrument, InstrumentStore
from vxl.instrument.config import FixedRoutingRule, SplitRoutingRule, TaskPatch
from vxl.instrument.errors import OperationRejectedError
from vxl.instrument.traversal import TileOrder


async def test_task_tiles_resolve_rules_at_task_positions(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    await instrument.set_traversal(TileOrder.CUSTOM)
    await instrument.set_routing_rule(
        "excitation_side", SplitRoutingRule(type="split", axis="x", threshold=5, lower="left", upper="right")
    )
    await instrument.add_tasks([(4, 0), (5, 0)])
    assert [tile.routes for tile in instrument.task_tiles.value] == [
        {"excitation_side": "left"},
        {"excitation_side": "right"},
    ]

    await instrument.set_routing_rule("excitation_side", FixedRoutingRule(type="fixed", route="right"))
    assert [tile.routes for tile in instrument.task_tiles.value] == [
        {"excitation_side": "right"},
        {"excitation_side": "right"},
    ]


@pytest.mark.parametrize("explicit_profiles", [False, True])
async def test_add_batch_replays_exact_ids_values_and_order(instrument: Instrument, explicit_profiles: bool) -> None:
    state = instrument.state.value
    xy = [(float(index), float(index * 2)) for index in range(20)]
    profiles = list(state.imaging.profiles) if explicit_profiles else None
    await instrument.add_tasks(xy, profile_ids=profiles)
    added = list(instrument.state.value.tasks.items())

    assert len(added) == 20
    assert [(task.x, task.y) for _, task in added] == xy
    assert all(
        task.profile_ids == (profiles if profiles is not None else [instrument.active_profile_id.value])
        and task.start == state.stencil.z_start
        and task.end == state.stencil.z_end
        for _, task in added
    )

    await instrument.undo()
    assert instrument.state.value.tasks == {}
    assert instrument.history.value.undo_label is None
    await instrument.redo()
    assert list(instrument.state.value.tasks.items()) == added
    assert list(InstrumentStore.load(instrument.path).value.tasks.items()) == added


@pytest.mark.parametrize("indices", [(3, 1), (4, 0), (4, 3, 2, 1, 0)])
async def test_remove_batch_restores_custom_order(instrument: Instrument, indices: tuple[int, ...]) -> None:
    await instrument.set_traversal(TileOrder.CUSTOM)
    await instrument.add_tasks([(4, 0), (1, 0), (3, 0), (0, 0), (2, 0)])
    original = list(instrument.state.value.tasks.items())
    removed = [original[index][0] for index in indices]
    remaining = [(uid, task) for uid, task in original if uid not in removed]

    await instrument.remove_tasks(removed)
    assert list(instrument.state.value.tasks.items()) == remaining
    assert [tile.task_id for tile in instrument.task_tiles.value] == [uid for uid, _ in remaining]

    await instrument.undo()
    assert list(instrument.state.value.tasks.items()) == original
    assert [tile.task_id for tile in instrument.task_tiles.value] == [uid for uid, _ in original]
    assert list(InstrumentStore.load(instrument.path).value.tasks.items()) == original

    await instrument.redo()
    assert list(instrument.state.value.tasks.items()) == remaining
    assert [tile.task_id for tile in instrument.task_tiles.value] == [uid for uid, _ in remaining]


async def test_update_batch_replays_only_affected_tasks(instrument: Instrument) -> None:
    await instrument.add_tasks([(0, 0), (1, 1), (2, 2)])
    original = instrument.state.value.tasks
    first, untouched, last = original
    other_profile = next(
        uid for uid in instrument.state.value.imaging.profiles if uid != instrument.active_profile_id.value
    )
    await instrument.update_tasks(
        {last: TaskPatch(start=2, end=10, profile_ids=[other_profile]), first: TaskPatch(x=5, y=6)}
    )
    updated = instrument.state.value.tasks
    assert list(updated) == list(original)
    assert updated[untouched] == original[untouched]
    assert updated[first] == original[first].model_copy(update={"x": 5, "y": 6})
    assert updated[last] == original[last].model_copy(update={"start": 2, "end": 10, "profile_ids": [other_profile]})

    await instrument.undo()
    assert list(instrument.state.value.tasks.items()) == list(original.items())
    await instrument.redo()
    assert list(instrument.state.value.tasks.items()) == list(updated.items())


@pytest.mark.parametrize("operation", ["add", "remove", "update", "invalid_profile"])
async def test_invalid_batch_preserves_state_disk_and_history(instrument: Instrument, operation: str) -> None:
    await instrument.add_tasks([(0, 0), (1, 1)])
    first = next(iter(instrument.state.value.tasks))
    await instrument.update_tasks({first: TaskPatch(x=2)})
    await instrument.undo()
    state = instrument.state.value
    history = instrument.history.value
    persisted = (instrument.path / "state.json").read_bytes()
    edits = {
        "add": lambda: instrument.add_tasks([(2, 2)], profile_ids=["missing"]),
        "remove": lambda: instrument.remove_tasks([first, "missing"]),
        "update": lambda: instrument.update_tasks({first: TaskPatch(x=5), "missing": TaskPatch(x=6)}),
        "invalid_profile": lambda: instrument.update_tasks({first: TaskPatch(profile_ids=["missing"])}),
    }

    with pytest.raises(OperationRejectedError, match="missing"):
        await edits[operation]()

    assert instrument.state.value == state
    assert instrument.history.value == history
    assert (instrument.path / "state.json").read_bytes() == persisted
    await instrument.redo()
    assert instrument.state.value.tasks[first].x == 2


@pytest.mark.parametrize("operation", ["add", "remove", "update", "unchanged"])
async def test_noop_batch_preserves_redo(instrument: Instrument, operation: str) -> None:
    await instrument.add_tasks([(0, 0)])
    first = next(iter(instrument.state.value.tasks))
    await instrument.update_tasks({first: TaskPatch(x=1)})
    await instrument.undo()
    state = instrument.state.value
    history = instrument.history.value

    match operation:
        case "add":
            await instrument.add_tasks([])
        case "remove":
            await instrument.remove_tasks([])
        case "update":
            await instrument.update_tasks({})
        case "unchanged":
            await instrument.update_tasks({first: TaskPatch(x=0)})

    assert instrument.state.value == state
    assert instrument.history.value == history
    await instrument.redo()
    assert instrument.state.value.tasks[first].x == 1
