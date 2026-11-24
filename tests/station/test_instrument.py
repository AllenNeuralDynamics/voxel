"""What every instrument does, shown on :class:`BasicInstrument`: its files, its saved state and edits, profiles,
device edits, timelines and the scheduler."""

import asyncio
import copy
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from rigup.activity import ActivityBusyError, ActivityInfo

from vxl._utils.files import load_yaml
from vxl.devices.signals.generator.base import OwnClock
from vxl.instrument.basic import BasicInstrument
from vxl.instrument.config import new_instrument_id
from vxl.instrument.folder import InstrumentFolder
from vxl.instrument.samples import render
from vxl.instrument.signals import Timeline
from vxl.instrument.state import InstrumentState, StageFollowRule, Task
from vxl.instrument.store import ABSENT, InstrumentStore, Merge
from vxl.station.errors import NotFoundError, RejectedError, StartupError

from .support import basic, codes, load, problems, profile, rig, simulated, template

# --- the files ---


def test_new_ids_are_26_safe_characters_and_differ() -> None:
    ids = {new_instrument_id() for _ in range(1000)}
    assert len(ids) == 1000
    assert all(len(i) == 26 and set(i) <= set("0123456789abcdefghjkmnpqrstvwxyz") for i in ids)


@pytest.mark.parametrize(
    "bad_id",
    [
        "6f1c2b8e-4d0a-4c1e-9b7f-2a5e8d3c1f40",
        "8x8k2m9q4r7t1v3w6y0z2b4c8d",
        "5x8k2m9q4r7t1v3w6y0z2b4c8",
        "5X8K2M9Q4R7T1V3W6Y0Z2B4C8D",
    ],
)
def test_ids_must_be_the_short_form(bad_id: str) -> None:
    data = rig()
    data["id"] = bad_id
    with pytest.raises(ValidationError, match="id"):
        load(data)


def test_names_are_labels_of_at_most_32_characters() -> None:
    data = rig()
    data["name"] = "x" * 33
    with pytest.raises(ValidationError, match="name"):
        load(data)


def test_a_template_makes_instruments_with_new_ids(tmp_path: Path) -> None:
    first, second = (InstrumentFolder.create(template(rig()), name, tmp_path) for name in ("left", "right"))
    assert first.ok
    assert second.ok
    assert first.config is not None
    assert second.config is not None
    assert first.config.id != second.config.id
    assert (first.config.name, first.config.model) == ("left", "bench.v1")


def test_a_template_has_no_id(tmp_path: Path) -> None:
    data = rig()
    with_identity = template(data)
    with_identity["rig"] |= {"id": data["id"], "name": data["name"]}
    with pytest.raises(RejectedError, match="a template has no id and no name"):
        InstrumentFolder.create(with_identity, "left", tmp_path)


def test_a_default_has_no_plan(tmp_path: Path) -> None:
    assert InstrumentState.default_fields() == {"metadata_cls", "positions", "profiles"}

    data = rig()
    data["default"]["plan"] = []
    assert InstrumentFolder.create(template(data), "left", tmp_path).problems.codes() == ["default.not_default"]


# --- the store ---


def _store(tmp_path: Path) -> InstrumentStore:
    folder = InstrumentFolder.create(template(rig()), "left", tmp_path)
    assert folder.config is not None
    assert isinstance(folder.default, InstrumentState)
    return InstrumentStore(folder.home, folder.config, folder.default, folder.default)


async def test_the_store_keeps_the_plan_out_of_the_defaults(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.value == store.default_state.value
    assert store.last_modified is None

    task = Task(id="brain", profiles=["gfp"], metadata={"notes": "left hemisphere"})
    await store.update({("plan",): [task], ("profiles", "gfp", "label"): "GFP"})
    assert store.last_modified is not None

    await store.save_as_default_state()
    assert store.default_state.value.profiles["gfp"].label == "GFP"
    assert set(load_yaml(store.home / "default.yaml")) <= InstrumentState.default_fields()
    with pytest.raises(RejectedError, match="plan"):
        await store.save_as_default_state(["plan"])

    await store.update({("profiles", "gfp", "label"): "green"})
    await store.update(store.default_values())
    assert (store.value.profiles["gfp"].label, store.value.plan[0].metadata) == ("GFP", {"notes": "left hemisphere"})

    with pytest.raises(RejectedError, match="'x_axis' is not a device of 'optics'"):
        await store.update({("positions", "x_axis"): 10})

    again = InstrumentFolder.read(store.home)
    assert again.ok
    assert (again.default, again.state) == (store.default_state.value, store.value)


async def test_the_store_sets_and_removes_values_at_key_paths(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gfp = store.value.profiles["gfp"].model_dump()

    added = await store.update({("profiles", "rfp"): gfp | {"positions": {"fw": "RFP"}}})
    assert set(store.value.profiles) == {"gfp", "rfp"}
    assert added.before == {("profiles", "rfp"): ABSENT}

    removed = await store.update({("profiles", "rfp"): ABSENT})
    assert set(store.value.profiles) == {"gfp"}
    assert removed.after == {("profiles", "rfp"): ABSENT}

    with pytest.raises(RejectedError) as caught:
        await store.update({("profiles", "rfp", "label"): "red"})
    assert [(problem.code, problem.loc) for problem in caught.value.problems] == [
        ("state.missing", ("profiles", "rfp", "label"))
    ]


async def test_a_merge_adds_keys_to_a_dict_and_makes_it_when_missing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    camera = ("profiles", "gfp", "props", "camera")

    made = await store.update({camera: Merge({"exposure_time_ms": 20.0})})
    await store.update({camera: Merge({"binning": 2})})
    await store.update({camera: Merge({"exposure_time_ms": 30.0})})
    assert store.value.profiles["gfp"].props["camera"] == {"exposure_time_ms": 30.0, "binning": 2}
    assert made.before == {camera: ABSENT}

    for path in (("profiles", "rfp", "props", "camera"), ("profiles", "gfp", "desc")):
        with pytest.raises(RejectedError) as caught:
            await store.update({path: Merge({"a": 1})})
        assert [problem.loc for problem in caught.value.problems] == [path]


# --- positions ---

_FOLLOW_X = {"axis": "x", "order": ["left", "right"], "at": [12000], "margin": 50}


def _two_arms(data: dict[str, Any]) -> dict[str, Any]:
    """Add a switch that sends the laser to 1 of 2 arms."""
    data["devices"]["arm_switch"] = {"target": "builtins.object", "init": {"slots": {"0": "left", "1": "right"}}}
    data["parts"].update(left_lens={"kind": "lens"}, right_lens={"kind": "lens"})
    data["optics"].update(
        laser={"to": "arm_switch"},
        arm_switch={"to": {"left": "left_lens", "right": "right_lens"}},
        left_lens={"to": "galvo"},
        right_lens={"to": "galvo"},
    )
    return data


@pytest.mark.parametrize(
    ("positions", "found"),
    [
        ({}, ["profile.position.missing"]),
        ({"arm_switch": _FOLLOW_X}, []),
        ({"arm_switch": "left"}, []),
        ({"arm_switch": "left", "fw": "GFP"}, ["profile.position.two_levels"]),
        ({"arm_switch": "left", "x_axis": 10}, ["positions.unexpected"]),
    ],
)
def test_the_positions_of_the_instrument(positions: dict[str, Any], found: list[str]) -> None:
    data = _two_arms(rig())
    data["default"]["positions"] = positions
    assert codes(data) == found


def test_a_device_gets_its_position_from_the_instrument_or_from_each_profile() -> None:
    data = rig()
    data["default"]["positions"] = {"fw": "GFP"}
    profile(data)["positions"] = {}
    assert codes(data) == []

    profile(data)["positions"] = {"fw": "RFP"}
    assert [(p.code, p.loc) for p in problems(data)] == [
        ("profile.position.two_levels", ("default", "profiles", "gfp", "positions", "fw"))
    ]


def test_a_device_that_1_profile_sets_each_profile_sets() -> None:
    data = rig()
    profiles = data["default"]["profiles"]
    data["devices"]["focus"] = {"target": "builtins.object"}
    data["optics"]["objective"]["to"] = "focus"
    data["optics"]["focus"] = {"to": "fw"}
    profiles["rfp"] = {**profiles["gfp"], "positions": {"fw": "RFP"}}
    assert codes(data) == []

    profiles["gfp"]["positions"]["focus"] = 120.5
    assert [(p.code, p.loc) for p in problems(data)] == [
        ("profile.position.not_in_all_profiles", ("default", "profiles", "rfp", "positions", "focus"))
    ]

    profiles["rfp"]["positions"]["focus"] = 118.0
    assert codes(data) == []


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"at": [100, 200]}, "2 positions in 'order' need 1 in 'at', got 2"),
        ({"order": ["left", "middle", "right"]}, "3 positions in 'order' need 2 in 'at', got 1"),
        ({"order": ["left", "middle", "right"], "at": [200, 100]}, "'at' must rise"),
        ({"order": ["left", "left"]}, "each item must appear once"),
        ({"margin": -1}, "greater than or equal to 0"),
    ],
)
def test_follow_rule_rules(change: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        StageFollowRule.model_validate({**_FOLLOW_X, **change})


def test_a_device_that_follows_the_stage_keeps_its_position_inside_the_margin() -> None:
    rule = StageFollowRule(axis="x", order=["left", "right"], at=[100], margin=10)
    assert [rule.position(coordinate) for coordinate in (95, 105)] == ["left", "right"]
    assert rule.position(105, previous="left") == "left"
    assert rule.position(111, previous="left") == "right"
    assert rule.position(95, previous="right") == "right"
    assert rule.position(89, previous="right") == "left"


# --- edits on a closed instrument ---


async def test_quick_position_edits_are_1_undo_step(tmp_path: Path) -> None:
    data = rig()
    del profile(data)["positions"]
    instrument = basic(data, tmp_path)
    for at in (4000, 4500, 5000):
        rule = StageFollowRule(axis="x", order=["GFP", "RFP"], at=[at])
        await instrument.set_position_rule("fw", rule, edit_id="drag")
    assert instrument.view.value.state.positions["fw"] == rule

    await instrument.undo()
    assert "fw" not in instrument.view.value.state.positions
    assert instrument.view.value.history.undo_label is None


async def test_task_edits_keep_their_order_and_undo_in_turn(tmp_path: Path) -> None:
    data = rig()
    data["default"]["profiles"]["rfp"] = copy.deepcopy(profile(data)) | {"positions": {"fw": "RFP"}}
    instrument = basic(data, tmp_path)
    for task_id in ("a", "b", "c"):
        await instrument.add_task(Task(id=task_id, profiles=["gfp"]))
    for profiles in (["rfp"], ["gfp", "rfp"], ["rfp"]):
        await instrument.update_task("b", profiles=profiles, edit_id="typing")
    await instrument.reorder_tasks(["c", "a", "b"])
    await instrument.remove_tasks(["a"])
    plan = instrument.view.value.state.plan
    assert [(task.id, task.profiles) for task in plan] == [("c", ["gfp"]), ("b", ["rfp"])]

    await instrument.undo()
    await instrument.undo()
    assert [task.id for task in instrument.view.value.state.plan] == ["a", "b", "c"]
    await instrument.undo()
    assert instrument.view.value.state.plan[1].profiles == ["gfp"]
    assert instrument.view.value.history.undo_label == "Add task"


async def test_task_edits_that_name_unknown_tasks_are_refused(tmp_path: Path) -> None:
    instrument = basic(rig(), tmp_path)
    await instrument.add_task(Task(id="a", profiles=["gfp"]))

    with pytest.raises(RejectedError, match="task ids must be unique"):
        await instrument.add_task(Task(id="a", profiles=["gfp"]))
    with pytest.raises(NotFoundError, match="No task 'z'"):
        await instrument.update_task("z", profiles=["gfp"])
    with pytest.raises(NotFoundError, match="No task 'z'"):
        await instrument.remove_tasks(["a", "z"])
    with pytest.raises(RejectedError, match="each task of the plan 1 time"):
        await instrument.reorder_tasks(["a", "a"])
    assert [task.id for task in instrument.view.value.state.plan] == ["a"]


# --- an open instrument ---


@pytest.fixture
async def opened(tmp_path: Path) -> AsyncIterator[BasicInstrument]:
    """An open instrument on simulated devices. Profile ``gfp`` sets the camera's exposure to 20 ms, ``slow`` to
    30 ms, and ``bad`` to a value the camera refuses."""
    data = simulated(rig())
    profiles = data["default"]["profiles"]
    profiles["gfp"]["props"] = {"camera": {"exposure_time_ms": 20.0}}
    profiles["slow"] = copy.deepcopy(profiles["gfp"]) | {"props": {"camera": {"exposure_time_ms": 30.0}}}
    profiles["bad"] = copy.deepcopy(profiles["gfp"]) | {"props": {"camera": {"exposure_time_ms": "fast"}}}
    instrument = basic(data, tmp_path)
    await instrument.open()
    yield instrument
    await instrument.close()


async def _exposure(instrument: BasicInstrument) -> float:
    results = await instrument.get_device_properties("camera", ["exposure_time_ms"])
    return results.results["exposure_time_ms"].unwrap().value


async def _filter_slot(instrument: BasicInstrument) -> int | None:
    return (await instrument.get_device_properties("fw", ["state"])).results["state"].unwrap().value["slot"]


async def _nothing() -> None:
    pass


@asynccontextmanager
async def _activity(instrument: BasicInstrument, kind: str, requires: set[Any]) -> AsyncGenerator[list[str]]:
    """Start an activity of ``kind`` that holds ``requires``, and give the list where its restarts are noted. A
    capture has no restart, so a command that needs what it holds is refused."""
    seen: list[str] = []

    @asynccontextmanager
    async def restart() -> AsyncGenerator[None]:
        seen.append("stop")
        yield
        seen.append("start")

    async with instrument._scheduler.run(f"start a {kind}", requires=()):
        activity = await instrument._scheduler.start(
            ActivityInfo(kind=kind), requires, stop=_nothing, restart=None if kind == "capture" else restart
        )
    try:
        yield seen
    finally:
        await activity.end()


async def test_opening_sets_the_devices_to_the_first_profile(opened: BasicInstrument) -> None:
    assert opened.view.value.active_profile == "gfp"
    assert await _exposure(opened) == pytest.approx(20.0)
    assert await _filter_slot(opened) == 0


async def test_selecting_a_profile_sets_its_devices_and_makes_it_active(opened: BasicInstrument) -> None:
    await opened.execute_device_command("fw", "move_to", ["RFP"], {"wait": True})
    await opened.select_profile("slow")
    assert opened.view.value.active_profile == "slow"
    assert await _exposure(opened) == pytest.approx(30.0)
    assert await _filter_slot(opened) == 0


async def test_applying_the_profile_again_undoes_live_changes(opened: BasicInstrument) -> None:
    await opened._hal.device("camera").props.set(exposure_time_ms=50.0)  # straight to the device: nothing saved
    await opened.apply_profile()
    assert await _exposure(opened) == pytest.approx(20.0)


async def test_a_failed_or_unknown_profile_keeps_the_active_one(opened: BasicInstrument) -> None:
    with pytest.raises(RejectedError, match="refused the properties"):
        await opened.select_profile("bad")
    with pytest.raises(NotFoundError, match="No profile 'missing'"):
        await opened.select_profile("missing")
    assert opened.view.value.active_profile == "gfp"


async def test_selecting_a_profile_restarts_what_holds_it_and_waits_for_a_capture(opened: BasicInstrument) -> None:
    async with _activity(opened, "preview", {opened._active_profile}) as seen:
        await opened.select_profile("slow")
    assert seen == ["stop", "start"]

    async with _activity(opened, "capture", {"camera"}):
        with pytest.raises(ActivityBusyError, match="Selecting profile gfp is not possible while capture is running"):
            await opened.select_profile("gfp")


def _saved_camera_props(instrument: BasicInstrument) -> dict[str, Any]:
    return instrument.view.value.state.profiles["gfp"].props.get("camera", {})


async def test_an_autosaved_edit_is_saved_as_the_device_reports_it(opened: BasicInstrument) -> None:
    results = await opened.set_device_properties("camera", {"exposure_time_ms": 30.0})
    reported = results.results["exposure_time_ms"].unwrap().value
    assert reported == pytest.approx(30.0)
    assert _saved_camera_props(opened)["exposure_time_ms"] == reported
    assert opened.view.value.history.undo_label is None


@pytest.mark.parametrize(
    ("device", "properties"),
    [("camera", {"binning": 2}), ("x_axis", {"speed": 5.0}), ("camera", {"exposure_time_ms": "fast"})],
    ids=["not on the autosave list", "off the light paths", "refused by the device"],
)
async def test_an_edit_that_is_not_kept_is_not_saved(
    opened: BasicInstrument, device: str, properties: dict[str, Any]
) -> None:
    before = opened.view.value.state
    await opened.set_device_properties(device, properties)
    assert opened.view.value.state == before


async def test_a_property_edit_keeps_a_running_activity_and_waits_for_a_capture(opened: BasicInstrument) -> None:
    async with _activity(opened, "preview", {opened._active_profile}) as seen:
        await opened.set_device_properties("camera", {"exposure_time_ms": 30.0})
    assert seen == []

    async with _activity(opened, "capture", {opened._store}):
        with pytest.raises(ActivityBusyError):
            await opened.set_device_properties("camera", {"exposure_time_ms": 30.0})


@pytest.mark.parametrize(
    ("device", "command"), [("camera", "capture_state"), ("x_axis", "halt")], ids=["query", "failsafe"]
)
async def test_a_query_or_failsafe_runs_while_another_command_holds_the_instrument(
    opened: BasicInstrument, device: str, command: str
) -> None:
    holding, release = asyncio.Event(), asyncio.Event()

    async def hold() -> None:
        async with opened._scheduler.run("a long command", requires=()):
            holding.set()
            await release.wait()

    holder = asyncio.create_task(hold())
    await holding.wait()
    try:
        result = await asyncio.wait_for(opened.execute_device_command(device, command), 2)
    finally:
        release.set()
        await holder
    assert result.is_ok


# --- timelines ---


async def _loaded(instrument: BasicInstrument) -> dict[str, list[float]]:
    """The volts on each pin that ``ao_main`` has loaded."""
    cycle = await instrument._hal.signal_generators["ao_main"].get_loaded()
    assert cycle is not None
    return cycle.volts


def _rendered(instrument: BasicInstrument, timeline: Timeline) -> dict[str, list[float]]:
    wires = instrument.config.wiring.outputs("ao_main")
    return {wires[name].pin: s.volts.tolist() for name, s in render(timeline, wires).wires.items()}


def _with_laser_offset(timeline: Timeline, offset: str) -> Timeline:
    data = timeline.model_dump(mode="json")
    data["signals"]["laser"]["start"]["offset"] = offset
    return Timeline.model_validate(data)


async def test_opening_loads_the_active_profiles_timelines_on_the_generators_own_clock(opened: BasicInstrument) -> None:
    timeline = opened.view.value.state.profiles["gfp"].timelines["ao_main"]
    cycle = await opened._hal.signal_generators["ao_main"].get_loaded()
    assert cycle is not None
    assert (cycle.volts, cycle.start) == (_rendered(opened, timeline), OwnClock())


async def test_a_new_timeline_is_loaded_then_saved(opened: BasicInstrument) -> None:
    timeline = _with_laser_offset(opened.view.value.state.profiles["gfp"].timelines["ao_main"], "-2 ms")
    await opened.set_generator_timeline("ao_main", timeline)
    assert await _loaded(opened) == _rendered(opened, timeline)
    assert opened.view.value.state.profiles["gfp"].timelines["ao_main"] == timeline
    assert opened.view.value.history.undo_label is None


async def test_a_timeline_that_does_not_fit_is_refused_before_the_generator_changes(opened: BasicInstrument) -> None:
    before_loaded, before_state = await _loaded(opened), opened.view.value.state
    data = opened.view.value.state.profiles["gfp"].timelines["ao_main"].model_dump(mode="json")
    data["duration"] = "100.05 ms"  # not a whole number of samples at 10 kHz
    with pytest.raises(RejectedError, match="whole number of samples"):
        await opened.set_generator_timeline("ao_main", Timeline.model_validate(data))
    assert (await _loaded(opened), opened.view.value.state) == (before_loaded, before_state)


async def test_a_timeline_edit_restarts_what_holds_the_profile_and_waits_for_a_capture(opened: BasicInstrument) -> None:
    timeline = _with_laser_offset(opened.view.value.state.profiles["gfp"].timelines["ao_main"], "-2 ms")
    async with _activity(opened, "preview", {opened._active_profile}) as seen:
        await opened.set_generator_timeline("ao_main", timeline)
    assert seen == ["stop", "start"]

    async with _activity(opened, "capture", {opened._store}):
        with pytest.raises(ActivityBusyError):
            await opened.set_generator_timeline("ao_main", timeline)


async def test_the_hal_finds_a_signal_generator_by_id(opened: BasicInstrument) -> None:
    hal = opened._hal
    assert hal.signal_generator("ao_main") is hal.signal_generators["ao_main"]
    with pytest.raises(NotFoundError, match="'camera' is not a signal generator"):
        hal.signal_generator("camera")


async def test_the_hal_finds_an_area_camera_by_id(opened: BasicInstrument) -> None:
    hal = opened._hal
    assert hal.area_camera("camera") is hal.area_cameras["camera"]
    with pytest.raises(NotFoundError, match="'ao_main' is not an area camera"):
        hal.area_camera("ao_main")


# --- what stops the opening ---


async def test_a_position_that_names_no_slot_stops_the_opening(tmp_path: Path) -> None:
    data = simulated(rig())
    profile(data)["positions"] = {"fw": "BFP"}
    with pytest.raises(StartupError) as caught:
        await basic(data, tmp_path).open()
    assert [(p.code, p.loc) for p in caught.value.problems] == [
        ("position.no_such_slot", ("profiles", "gfp", "positions", "fw"))
    ]


async def test_a_wire_on_a_pin_the_generator_does_not_have_stops_the_opening(tmp_path: Path) -> None:
    data = simulated(rig())
    data["wiring"]["ao_main"]["galvo"]["pin"] = "ao99"
    with pytest.raises(StartupError) as caught:
        await basic(data, tmp_path).open()
    assert [(p.code, p.loc) for p in caught.value.problems] == [
        ("rig.wiring.unknown_pin", ("wiring", "ao_main", "galvo", "pin"))
    ]
