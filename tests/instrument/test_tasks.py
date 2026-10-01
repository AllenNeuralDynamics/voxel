import pytest

from vxl.instrument import (
    AcquisitionTask,
    Instrument,
    InstrumentStore,
    Point2D,
    TaskPatch,
    TileOrder,
    XYDefinition,
    XYMode,
    ZRange,
)
from vxl.instrument.config import SplitRoutingRule
from vxl.instrument.errors import OperationRejectedError
from vxl.instrument.planning import resolve_xy


def _task(
    task_id: str,
    xy: list[tuple[float, float]],
    profiles: list[str],
    *,
    start: float = 0,
    end: float = 10,
) -> AcquisitionTask:
    return AcquisitionTask(
        id=task_id,
        xy=XYDefinition(mode=XYMode.EXPLICIT_POINTS, points=[Point2D(x=x, y=y) for x, y in xy]),
        profiles=profiles,
        z=ZRange(start=start, end=end),
        traversal=TileOrder.CUSTOM,
    )


def _replace_position(x: float, y: float) -> TaskPatch:
    return TaskPatch(xy=XYDefinition(mode=XYMode.EXPLICIT_POINTS, points=[Point2D(x=x, y=y)]))


def test_tiled_rectangle_resolves_independent_axis_overlap() -> None:
    xy = XYDefinition(
        mode=XYMode.BOUNDING_BOX,
        points=[Point2D(x=2, y=3), Point2D(x=22, y=23)],
        overlap=Point2D(x=0.5, y=0),
    )

    assert resolve_xy(xy, width=10, height=10, traversal=TileOrder.CUSTOM) == [
        Point2D(x=7, y=8),
        Point2D(x=7, y=18),
        Point2D(x=12, y=8),
        Point2D(x=12, y=18),
        Point2D(x=17, y=8),
        Point2D(x=17, y=18),
    ]


def test_xy_definition_uses_shared_point_schema() -> None:
    xy = XYDefinition(
        mode=XYMode.BOUNDING_BOX,
        points=[Point2D(x=1, y=2), Point2D(x=3, y=4)],
    )

    assert xy.model_dump(mode="json") == {
        "mode": "bounding_box",
        "points": [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}],
        "overlap": {"x": 0.1, "y": 0.1},
    }


def test_tiled_convex_hull_ignores_point_order_and_interior_points() -> None:
    xy = XYDefinition(
        mode=XYMode.CONVEX_HULL,
        points=[
            Point2D(x=20, y=20),
            Point2D(x=0, y=0),
            Point2D(x=10, y=10),
            Point2D(x=0, y=20),
            Point2D(x=20, y=0),
        ],
        overlap=Point2D(x=0, y=0),
    )

    assert resolve_xy(xy, width=10, height=10, traversal=TileOrder.CUSTOM) == [
        Point2D(x=5, y=5),
        Point2D(x=5, y=15),
        Point2D(x=15, y=5),
        Point2D(x=15, y=15),
    ]


@pytest.mark.parametrize("instrument_config", ["split-x"], indirect=True)
async def test_planned_volumes_resolve_rules_at_task_positions(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    profile = instrument.active_profile_id.value
    await instrument.set_routing_rule("excitation_side", SplitRoutingRule(threshold=5))
    await instrument.add_task(_task("task", [(4, 0), (5, 0)], [profile], start=0, end=0))
    assert [volume.routes for volume in instrument.planned_volumes.value] == [
        {"excitation_side": "lower"},
        {"excitation_side": "upper"},
    ]

    await instrument.set_routing_rule("excitation_side", SplitRoutingRule(threshold=0))
    assert [volume.routes for volume in instrument.planned_volumes.value] == [
        {"excitation_side": "upper"},
        {"excitation_side": "upper"},
    ]


@pytest.mark.parametrize("explicit_profiles", [False, True])
async def test_add_task_replays_exact_values(instrument: Instrument, explicit_profiles: bool) -> None:
    state = instrument.state.value
    xy = [(float(index), float(index * 2)) for index in range(20)]
    profiles = list(state.imaging.profiles) if explicit_profiles else [instrument.active_profile_id.value]
    task = _task("task", xy, profiles, start=3, end=7)

    await instrument.add_task(task)
    assert instrument.state.value.plan == [task]

    await instrument.undo()
    assert instrument.state.value.plan == []
    assert instrument.history.value.undo_label is None
    await instrument.redo()
    assert instrument.state.value.plan == [task]
    assert InstrumentStore.load(instrument.path).value.plan == [task]


@pytest.mark.parametrize("indices", [(3, 1), (4, 0), (4, 3, 2, 1, 0)])
async def test_remove_tasks_restores_plan_order(instrument: Instrument, indices: tuple[int, ...]) -> None:
    profile = instrument.active_profile_id.value
    for index, x in enumerate((4, 1, 3, 0, 2)):
        await instrument.add_task(_task(f"task-{index}", [(x, 0)], [profile]))
    original = instrument.state.value.plan
    removed = [original[index].id for index in indices]
    remaining = [task for task in original if task.id not in removed]

    await instrument.remove_tasks(removed)
    assert instrument.state.value.plan == remaining

    await instrument.undo()
    assert instrument.state.value.plan == original
    assert InstrumentStore.load(instrument.path).value.plan == original

    await instrument.redo()
    assert instrument.state.value.plan == remaining


async def test_update_task_replays_only_the_affected_task(instrument: Instrument) -> None:
    profiles = list(instrument.state.value.imaging.profiles)
    profile = instrument.active_profile_id.value
    other_profile = next(uid for uid in profiles if uid != profile)
    for index in range(3):
        await instrument.add_task(_task(f"task-{index}", [(index, index)], [profile]))
    original = instrument.state.value.plan
    target = original[0]
    patch = TaskPatch(
        xy=XYDefinition(mode=XYMode.EXPLICIT_POINTS, points=[Point2D(x=5, y=6)]),
        profiles=[other_profile],
        z=ZRange(start=2, end=10),
    )

    await instrument.update_task(target.id, patch)
    updated = instrument.state.value.plan
    assert [task.id for task in updated] == [task.id for task in original]
    assert updated[1:] == original[1:]
    assert updated[0] == target.model_copy(update=patch.changes())

    await instrument.undo()
    assert instrument.state.value.plan == original
    await instrument.redo()
    assert instrument.state.value.plan == updated


@pytest.mark.parametrize("operation", ["add", "remove", "update", "invalid_profile"])
async def test_invalid_edit_preserves_state_disk_and_history(instrument: Instrument, operation: str) -> None:
    profile = instrument.active_profile_id.value
    first = _task("first", [(0, 0)], [profile])
    await instrument.add_task(first)
    await instrument.add_task(_task("second", [(1, 1)], [profile]))
    await instrument.update_task(first.id, _replace_position(2, 0))
    await instrument.undo()
    state = instrument.state.value
    history = instrument.history.value
    persisted = (instrument.path / "state.json").read_bytes()

    async def apply_invalid_edit() -> None:
        match operation:
            case "add":
                await instrument.add_task(first)
            case "remove":
                await instrument.remove_tasks([first.id, "missing"])
            case "update":
                await instrument.update_task("missing", TaskPatch(profiles=[profile]))
            case "invalid_profile":
                await instrument.update_task(first.id, TaskPatch(profiles=["missing"]))

    with pytest.raises(OperationRejectedError):
        await apply_invalid_edit()

    assert instrument.state.value == state
    assert instrument.history.value == history
    assert (instrument.path / "state.json").read_bytes() == persisted
    await instrument.redo()
    updated = instrument.state.value.plan[0]
    assert updated.xy.mode is XYMode.EXPLICIT_POINTS
    assert updated.xy.points[0].x == 2


@pytest.mark.parametrize("operation", ["remove", "update", "reorder"])
async def test_noop_edit_preserves_redo(instrument: Instrument, operation: str) -> None:
    profile = instrument.active_profile_id.value
    task = _task("task", [(0, 0)], [profile])
    await instrument.add_task(task)
    await instrument.update_task(task.id, _replace_position(1, 0))
    await instrument.undo()
    state = instrument.state.value
    history = instrument.history.value

    match operation:
        case "remove":
            await instrument.remove_tasks([])
        case "update":
            await instrument.update_task(task.id, _replace_position(0, 0))
        case "reorder":
            await instrument.reorder_tasks([task.id])

    assert instrument.state.value == state
    assert instrument.history.value == history
    await instrument.redo()
    updated = instrument.state.value.plan[0]
    assert updated.xy.mode is XYMode.EXPLICIT_POINTS
    assert updated.xy.points[0].x == 1
