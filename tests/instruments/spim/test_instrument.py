import asyncio
import copy
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from ome_zarr_writer import WriterSettings
from pydantic import BaseModel, ValidationError
from rigup.activity import ActivityBusyError, ActivityInfo
from vxl_records import SQLiteRecords

from vxl._utils.files import load_yaml
from vxl.core.errors import RejectedError, StartupError
from vxl.core.instrument.config import new_instrument_id
from vxl.core.instrument.folder import InstrumentFolder
from vxl.core.instrument.samples import render
from vxl.core.instrument.signals import Timeline
from vxl.core.instrument.state import StageFollowRule
from vxl.core.instrument.store import ABSENT, InstrumentStore, Merge
from vxl.devices.camera.roi import AreaROI
from vxl.devices.signals.generator.base import OwnClock
from vxl.instruments.spim.config import SPIMConfig
from vxl.instruments.spim.instrument import Microscope
from vxl.instruments.spim.state import SPIMState, WriterFields
from vxl.instruments.spim.task import Task, TaskFields
from vxl.system import System

from .support import codes, load, simulated, sweep_x, template, two_arms, two_cameras


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
def test_ids_must_be_the_short_form(config_data: dict[str, Any], bad_id: str) -> None:
    config_data["id"] = bad_id
    with pytest.raises(ValidationError, match="id"):
        load(config_data)


def test_names_are_labels_of_at_most_32_characters(config_data: dict[str, Any]) -> None:
    config_data["name"] = "x" * 33
    with pytest.raises(ValidationError, match="name"):
        load(config_data)


def test_a_template_makes_instruments_with_new_ids(config_data: dict[str, Any], tmp_path: Path) -> None:
    first, second = (InstrumentFolder.create(template(config_data), name, tmp_path) for name in ("left", "right"))
    assert first.ok
    assert second.ok
    assert first.config is not None
    assert second.config is not None
    assert first.config.id != second.config.id
    assert (first.config.name, first.config.model) == ("left", "exaspim.v2")


def test_a_template_has_no_id(config_data: dict[str, Any], tmp_path: Path) -> None:
    with_identity = template(config_data)
    with_identity["rig"] |= {"id": config_data["id"], "name": config_data["name"]}
    with pytest.raises(RejectedError, match="a template has no id and no name"):
        InstrumentFolder.create(with_identity, "left", tmp_path)


def test_a_default_has_no_plan_and_no_metadata(config_data: dict[str, Any], tmp_path: Path) -> None:
    assert SPIMState.default_fields() == {"metadata_cls", "writer", "task", "positions", "profiles"}

    config_data["default"]["metadata"] = {"notes": "left hemisphere"}
    assert InstrumentFolder.create(template(config_data), "left", tmp_path).problems.codes() == ["default.not_default"]


async def test_the_store_keeps_the_plan_and_the_metadata_out_of_the_defaults(
    config_data: dict[str, Any], tmp_path: Path
) -> None:
    folder = InstrumentFolder.create(template(config_data), "left", tmp_path)
    home = folder.home
    assert isinstance(folder.config, SPIMConfig)
    assert isinstance(folder.default, SPIMState)
    store = InstrumentStore(home, folder.config, folder.default, folder.default)
    assert store.value == store.default_state.value
    assert store.last_modified is None

    xy = {"kind": "bounding_box", "points": [{"x": 0, "y": 0}, {"x": 500, "y": 500}]}
    region = {"outline": xy, "bounds": [0, 100]}
    task = Task.complete({"id": "brain", "region": region, "profiles": ["gfp"]}, store.value.task)
    await store.update(
        {("plan",): [task], ("metadata",): {"notes": "left hemisphere"}, ("profiles", "gfp", "spacing"): 2.0}
    )
    assert store.last_modified is not None

    await store.save_as_default_state()
    assert store.default_state.value.profiles["gfp"].spacing == 2.0
    assert set(load_yaml(home / "default.yaml")) <= SPIMState.default_fields()
    with pytest.raises(RejectedError, match="plan"):
        await store.save_as_default_state(["plan"])

    await store.update({("profiles", "gfp", "spacing"): 3.0})
    await store.update(store.default_values())
    assert (store.value.profiles["gfp"].spacing, len(store.value.plan)) == (2.0, 1)
    assert store.value.metadata == {"notes": "left hemisphere"}

    with pytest.raises(RejectedError, match="'x_axis' is not a device of 'optics'"):
        await store.update({("positions", "x_axis"): 10})
    assert store.value.positions == store.default_state.value.positions

    again = InstrumentFolder.read(home)
    assert again.ok
    assert again.default == store.default_state.value
    assert again.state == store.value


async def test_the_store_sets_and_removes_values_at_key_paths(config_data: dict[str, Any], tmp_path: Path) -> None:
    folder = InstrumentFolder.create(template(config_data), "left", tmp_path)
    assert isinstance(folder.config, SPIMConfig)
    assert isinstance(folder.default, SPIMState)
    store = InstrumentStore(folder.home, folder.config, folder.default, folder.default)
    gfp = store.value.profiles["gfp"].model_dump()

    added = await store.update({("profiles", "rfp"): gfp | {"positions": {"fw": "RFP"}}})
    assert set(store.value.profiles) == {"gfp", "rfp"}
    assert added.before == {("profiles", "rfp"): ABSENT}

    removed = await store.update({("profiles", "rfp"): ABSENT})
    assert set(store.value.profiles) == {"gfp"}
    assert removed.after == {("profiles", "rfp"): ABSENT}

    with pytest.raises(RejectedError) as caught:
        await store.update({("profiles", "rfp", "spacing"): 2.0})
    assert [(problem.code, problem.loc) for problem in caught.value.problems] == [
        ("state.missing", ("profiles", "rfp", "spacing"))
    ]


async def test_a_merge_adds_keys_to_a_dict_and_makes_it_when_missing(
    config_data: dict[str, Any], tmp_path: Path
) -> None:
    folder = InstrumentFolder.create(template(config_data), "left", tmp_path)
    assert isinstance(folder.config, SPIMConfig)
    assert isinstance(folder.default, SPIMState)
    store = InstrumentStore(folder.home, folder.config, folder.default, folder.default)
    camera = ("profiles", "gfp", "props", "camera")

    made = await store.update({camera: Merge({"exposure_time_ms": 20.0})})
    await store.update({camera: Merge({"binning": 2})})
    await store.update({camera: Merge({"exposure_time_ms": 30.0})})
    assert store.value.profiles["gfp"].props["camera"] == {"exposure_time_ms": 30.0, "binning": 2}
    assert made.before == {camera: ABSENT}

    for path in (("profiles", "rfp", "props", "camera"), ("profiles", "gfp", "spacing")):
        with pytest.raises(RejectedError) as caught:
            await store.update({path: Merge({"a": 1})})
        assert [problem.loc for problem in caught.value.problems] == [path]


def test_the_file_has_no_engine(config_data: dict[str, Any]) -> None:
    config_data["engine"] = {"target": "vxl.engines.spim.ClockedStep"}
    with pytest.raises(ValidationError, match=r"engine\s+Extra inputs are not permitted"):
        load(config_data)


_FOLLOW_X = {"axis": "x", "order": ["left", "right"], "at": [12000], "margin": 50}


@pytest.mark.parametrize(
    ("positions", "found"),
    [
        ({}, ["profile.position.missing"]),
        ({"arm_switch": _FOLLOW_X}, []),
        ({"arm_switch": "left"}, []),
        ({"arm_switch": "left", "fw": "GFP"}, ["profile.position.two_levels"]),
        ({"arm_switch": "left", "x_axis": 10}, ["positions.unexpected"]),
        ({"arm_switch": {**_FOLLOW_X, "axis": "z"}}, ["positions.follows_scan_axis"]),
    ],
)
def test_the_positions_of_the_instrument(
    config_data: dict[str, Any], positions: dict[str, Any], found: list[str]
) -> None:
    two_arms(config_data)
    config_data["default"]["positions"] = positions
    assert codes(load(config_data)) == found


def test_a_device_gets_its_position_from_the_instrument_or_from_each_profile(config_data: dict[str, Any]) -> None:
    gfp = config_data["default"]["profiles"]["gfp"]
    config_data["default"]["positions"] = {"fw": "GFP"}
    gfp["positions"] = {}
    assert codes(load(config_data)) == []

    gfp["positions"] = {"fw": "RFP"}
    example = load(config_data)
    assert codes(example) == ["profile.position.two_levels"]
    assert [problem.loc for problem in example.problems()] == [("default", "profiles", "gfp", "positions", "fw")]


def test_a_device_that_1_profile_sets_each_profile_sets(config_data: dict[str, Any]) -> None:
    hal, profiles = config_data, config_data["default"]["profiles"]
    hal["devices"]["focus"] = {"target": "builtins.object"}
    hal["optics"]["objective"]["to"] = "focus"
    hal["optics"]["focus"] = {"to": "fw"}
    profiles["rfp"] = {**profiles["gfp"], "positions": {"fw": "RFP"}}
    assert codes(load(config_data)) == []

    profiles["gfp"]["positions"]["focus"] = 120.5
    example = load(config_data)
    assert codes(example) == ["profile.position.not_in_all_profiles"]
    assert [problem.loc for problem in example.problems()] == [("default", "profiles", "rfp", "positions", "focus")]

    profiles["rfp"]["positions"]["focus"] = 118.0
    assert codes(load(config_data)) == []


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


_REGION = {"outline": {"kind": "explicit_points", "points": [{"x": 0, "y": 0}]}, "bounds": [0, 1]}


def _microscope(config_data: dict[str, Any], tmp_path: Path) -> Microscope:
    folder = InstrumentFolder.create(template(config_data), "left", tmp_path)
    records = SQLiteRecords(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    return Microscope(folder, records=records, system=system)


@pytest.fixture
def microscope(config_data: dict[str, Any], tmp_path: Path) -> Microscope:
    return _microscope(config_data, tmp_path)


def _task(microscope: Microscope, task_id: str) -> Task:
    return Task.complete({"id": task_id, "region": _REGION, "profiles": ["gfp"]}, microscope.view.value.state.task)


async def test_writer_spacing_and_profile_detail_edits_can_be_undone(microscope: Microscope) -> None:
    await microscope.update_writer_settings(shard_z_chunks=4, target_shard_gb=2.0)
    await microscope.set_spacing("gfp", 2.5)
    await microscope.update_profile_details("gfp", label="GFP", desc="green", channel_labels={"camera": "green"})
    state = microscope.view.value.state
    assert (state.writer.shard_z_chunks, state.profiles["gfp"].spacing) == (4, 2.5)
    assert (state.profiles["gfp"].label, state.profiles["gfp"].desc) == ("GFP", "green")
    assert state.profiles["gfp"].channels["camera"].label == "green"

    for _ in range(3):
        await microscope.undo()
    assert microscope.view.value.state == microscope.view.value.default_state


@pytest.mark.parametrize(
    ("profile_id", "spacing", "loc"),
    [("rfp", 2.0, ("profiles", "rfp", "spacing")), ("gfp", -1, ("profiles", "gfp", "spacing"))],
)
async def test_a_spacing_edit_is_refused_at_its_path(
    microscope: Microscope, profile_id: str, spacing: float, loc: tuple[str, ...]
) -> None:
    with pytest.raises(RejectedError) as caught:
        await microscope.set_spacing(profile_id, spacing)
    assert [problem.loc for problem in caught.value.problems] == [loc]
    assert microscope.view.value.history.undo_label is None


async def test_a_channel_label_for_a_camera_not_in_the_profile_is_refused(microscope: Microscope) -> None:
    with pytest.raises(RejectedError) as caught:
        await microscope.update_profile_details("gfp", channel_labels={"laser": "blue"})
    assert [problem.loc for problem in caught.value.problems] == [("profiles", "gfp", "channels", "laser", "label")]


@pytest.mark.parametrize("name", ["props", "spacing", "spcing"])
async def test_profile_details_cannot_change_other_fields(microscope: Microscope, name: str) -> None:
    untyped: dict[str, Any] = {name: {}}  # what a caller with no types can send
    with pytest.raises(RejectedError, match=f"cannot change \\['{name}'\\] of a profile"):
        await microscope.update_profile_details("gfp", **untyped)


@pytest.mark.parametrize(("fields", "model"), [(TaskFields, Task), (WriterFields, WriterSettings)])
def test_each_field_list_names_fields_of_its_model(fields: type, model: type[BaseModel]) -> None:
    assert fields.__annotations__.keys() <= model.model_fields.keys()


async def test_quick_position_edits_are_1_undo_step(config_data: dict[str, Any], tmp_path: Path) -> None:
    del config_data["default"]["profiles"]["gfp"]["positions"]
    microscope = _microscope(config_data, tmp_path)
    for at in (4000, 4500, 5000):
        rule = StageFollowRule(axis="x", order=["GFP", "RFP"], at=[at])
        await microscope.set_position_rule("fw", rule, edit_id="drag")
    assert microscope.view.value.state.positions["fw"] == rule

    await microscope.undo()
    assert "fw" not in microscope.view.value.state.positions
    assert microscope.view.value.history.undo_label is None


async def test_task_edits_keep_their_order_and_undo_in_turn(microscope: Microscope) -> None:
    for task_id in ("a", "b", "c"):
        await microscope.add_task(_task(microscope, task_id))
    for iteration in ("profile_major", "position_major", "profile_major"):
        await microscope.update_task("b", iteration=iteration, edit_id="typing")
    await microscope.reorder_tasks(["c", "a", "b"])
    await microscope.remove_tasks(["a"])
    assert [(task.id, task.iteration) for task in microscope.view.value.state.plan] == [
        ("c", "position_major"),
        ("b", "profile_major"),
    ]

    await microscope.undo()
    await microscope.undo()
    assert [task.id for task in microscope.view.value.state.plan] == ["a", "b", "c"]
    await microscope.undo()
    assert microscope.view.value.state.plan[1].iteration == "position_major"
    assert microscope.view.value.history.undo_label == "Add task"


async def test_task_edits_that_name_unknown_tasks_are_refused(microscope: Microscope) -> None:
    await microscope.add_task(_task(microscope, "a"))

    with pytest.raises(RejectedError, match="task ids must be unique"):
        await microscope.add_task(_task(microscope, "a"))
    with pytest.raises(RejectedError, match="No task 'z'"):
        await microscope.update_task("z", iteration="profile_major")
    with pytest.raises(RejectedError, match="No task 'z'"):
        await microscope.remove_tasks(["a", "z"])
    with pytest.raises(RejectedError, match="each task of the plan 1 time"):
        await microscope.reorder_tasks(["a", "a"])
    assert [task.id for task in microscope.view.value.state.plan] == ["a"]


@pytest.fixture
async def opened(config_data: dict[str, Any], tmp_path: Path) -> AsyncIterator[Microscope]:
    """An open microscope on simulated devices. Profile ``gfp`` sets the camera's exposure to 20 ms, ``slow`` to
    30 ms, and ``bad`` to a value the camera refuses."""
    profiles = config_data["default"]["profiles"]
    gfp = profiles["gfp"]
    gfp["props"] = {"camera": {"exposure_time_ms": 20.0}}
    profiles["slow"] = copy.deepcopy(gfp) | {"props": {"camera": {"exposure_time_ms": 30.0}}}
    profiles["bad"] = copy.deepcopy(gfp) | {"props": {"camera": {"exposure_time_ms": "fast"}}}
    microscope = _microscope(simulated(config_data), tmp_path)
    await microscope.open()
    yield microscope
    await microscope.close()


async def _exposure(microscope: Microscope) -> float:
    results = await microscope.get_device_properties("camera", ["exposure_time_ms"])
    return results.results["exposure_time_ms"].unwrap().value


async def _filter_slot(microscope: Microscope) -> int | None:
    return (await microscope.get_device_properties("fw", ["state"])).results["state"].unwrap().value["position"]


async def test_opening_sets_the_devices_to_the_first_profile(opened: Microscope) -> None:
    assert opened.view.value.active_profile == "gfp"
    assert await _exposure(opened) == pytest.approx(20.0)
    assert await _filter_slot(opened) == 0


async def test_selecting_a_profile_sets_its_devices_and_makes_it_active(opened: Microscope) -> None:
    await opened.execute_device_command("fw", "move_to", ["RFP"], {"wait": True})
    await opened.select_profile("slow")
    assert opened.view.value.active_profile == "slow"
    assert await _exposure(opened) == pytest.approx(30.0)
    assert await _filter_slot(opened) == 0


async def test_applying_the_profile_again_undoes_live_changes(opened: Microscope) -> None:
    await opened._hal.device("camera").props.set(exposure_time_ms=50.0)  # straight to the device: nothing saved
    await opened.apply_profile()
    assert await _exposure(opened) == pytest.approx(20.0)


async def test_a_failed_step_keeps_the_active_profile(opened: Microscope) -> None:
    with pytest.raises(RejectedError, match="refused the properties"):
        await opened.select_profile("bad")
    assert opened.view.value.active_profile == "gfp"


async def test_an_unknown_profile_is_refused(opened: Microscope) -> None:
    with pytest.raises(RejectedError, match="No profile 'missing'"):
        await opened.select_profile("missing")


async def test_a_capture_refuses_selecting_a_profile(opened: Microscope) -> None:
    scheduler = opened._scheduler
    async with scheduler.run("start a capture", requires=()):
        await scheduler.start(ActivityInfo(kind="capture"), {"camera"})
    with pytest.raises(ActivityBusyError, match="Unable to select a profile while capture is running"):
        await opened.select_profile("slow")


async def test_selecting_a_profile_restarts_an_activity_that_holds_the_active_profile(opened: Microscope) -> None:
    seen: list[str] = []

    @asynccontextmanager
    async def restart() -> AsyncGenerator[None]:
        seen.append(f"stop with {opened.view.value.active_profile}")
        yield
        seen.append(f"start with {opened.view.value.active_profile}")

    async with opened._scheduler.run("start a preview", requires=()):
        await opened._scheduler.start(ActivityInfo(kind="preview"), {opened._active_profile}, restart=restart)
    await opened.select_profile("slow")
    assert seen == ["stop with gfp", "start with slow"]


def _saved_camera_props(microscope: Microscope) -> dict[str, Any]:
    return microscope.view.value.state.profiles["gfp"].props.get("camera", {})


async def test_an_autosaved_edit_is_saved_as_the_device_reports_it(opened: Microscope) -> None:
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
    opened: Microscope, device: str, properties: dict[str, Any]
) -> None:
    before = opened.view.value.state
    await opened.set_device_properties(device, properties)
    assert opened.view.value.state == before


async def test_a_camera_region_is_saved_as_the_camera_snapped_it(opened: Microscope) -> None:
    applied = await opened.set_camera_region("camera", AreaROI(x=3, y=5, w=1001, h=999))
    assert opened.view.value.state.profiles["gfp"].channels["camera"].fov == applied

    full = await opened.set_camera_region("camera", None)
    assert (full.w, full.h) == (2048, 2048)
    assert opened.view.value.state.profiles["gfp"].channels["camera"].fov == full


async def test_device_first_edits_are_refused_during_a_capture(opened: Microscope) -> None:
    async with opened._scheduler.run("start a capture", requires=()):
        await opened._scheduler.start(ActivityInfo(kind="capture"), {opened._store})
    with pytest.raises(ActivityBusyError):
        await opened.set_device_properties("camera", {"exposure_time_ms": 30.0})
    with pytest.raises(ActivityBusyError):
        await opened.set_camera_region("camera", None)


async def test_a_property_edit_does_not_restart_a_preview(opened: Microscope) -> None:
    seen: list[str] = []

    @asynccontextmanager
    async def restart() -> AsyncGenerator[None]:
        seen.append("restarted")
        yield

    async with opened._scheduler.run("start a preview", requires=()):
        await opened._scheduler.start(ActivityInfo(kind="preview"), {opened._active_profile}, restart=restart)
    await opened.set_device_properties("camera", {"exposure_time_ms": 30.0})
    assert seen == []


async def test_a_position_that_names_no_slot_stops_the_opening(config_data: dict[str, Any], tmp_path: Path) -> None:
    config_data["default"]["profiles"]["gfp"]["positions"] = {"fw": "BFP"}
    microscope = _microscope(simulated(config_data), tmp_path)
    with pytest.raises(StartupError) as caught:
        await microscope.open()
    assert [(p.code, p.loc) for p in caught.value.problems] == [
        ("position.no_such_slot", ("profiles", "gfp", "positions", "fw"))
    ]


def _second_camera(data: dict[str, Any]) -> dict[str, Any]:
    """Add a switch after the filter wheel that sends the light to ``camera`` or to a second camera, ``camera2``.
    Every profile keeps ``camera``."""
    data["devices"]["det_switch"] = copy.deepcopy(data["devices"]["fw"])
    data["devices"]["det_switch"]["init"]["slots"] = {
        "0": {"label": "a", "position": 0},
        "1": {"label": "b", "position": 10},
    }
    data["devices"]["camera2"] = copy.deepcopy(data["devices"]["camera"])
    data["optics"].update(
        fw={"to": "det_switch"},
        det_switch={"to": {"a": "camera", "b": "camera2"}},
        camera2=copy.deepcopy(data["optics"]["camera"]),
    )
    data["default"]["profiles"]["gfp"]["positions"]["det_switch"] = "a"
    return data


async def test_a_region_on_a_camera_outside_the_active_profile_is_set_but_not_saved(
    config_data: dict[str, Any], tmp_path: Path
) -> None:
    microscope = _microscope(_second_camera(simulated(config_data)), tmp_path)
    await microscope.open()
    try:
        before = microscope.view.value.state
        applied = await microscope.set_camera_region("camera2", AreaROI(x=0, y=0, w=1024, h=1024))
        assert (applied.w, applied.h) == (1024, 1024)
        assert microscope.view.value.state == before
    finally:
        await microscope.close()


async def _loaded(microscope: Microscope) -> dict[str, list[float]]:
    """The volts on each pin that ``ao_main`` has loaded."""
    cycle = await microscope._hal.signal_generators["ao_main"].get_loaded()
    assert cycle is not None
    return cycle.volts


def _rendered(microscope: Microscope, timeline: Timeline) -> dict[str, list[float]]:
    wires = microscope.config.wiring.outputs("ao_main")
    return {wires[name].pin: s.volts.tolist() for name, s in render(timeline, wires).wires.items()}


async def test_opening_loads_the_active_profiles_timelines(opened: Microscope) -> None:
    timeline = opened.view.value.state.profiles["gfp"].timelines["ao_main"]
    assert await _loaded(opened) == _rendered(opened, timeline)


def _with_laser_offset(timeline: Timeline, offset: str) -> Timeline:
    data = timeline.model_dump(mode="json")
    data["signals"]["laser"]["start"]["offset"] = offset
    return Timeline.model_validate(data)


async def test_a_new_timeline_is_loaded_then_saved(opened: Microscope) -> None:
    timeline = _with_laser_offset(opened.view.value.state.profiles["gfp"].timelines["ao_main"], "-2 ms")
    await opened.set_generator_timeline("ao_main", timeline)
    assert await _loaded(opened) == _rendered(opened, timeline)
    assert opened.view.value.state.profiles["gfp"].timelines["ao_main"] == timeline
    assert opened.view.value.history.undo_label is None


async def test_a_timeline_that_does_not_fit_is_refused_before_the_generator_changes(opened: Microscope) -> None:
    before_loaded, before_state = await _loaded(opened), opened.view.value.state
    data = opened.view.value.state.profiles["gfp"].timelines["ao_main"].model_dump(mode="json")
    data["duration"] = "100.05 ms"  # not a whole number of samples at 10 kHz
    with pytest.raises(RejectedError, match="whole number of samples"):
        await opened.set_generator_timeline("ao_main", Timeline.model_validate(data))
    assert (await _loaded(opened), opened.view.value.state) == (before_loaded, before_state)


async def test_a_timeline_edit_restarts_a_preview_and_is_refused_during_a_capture(opened: Microscope) -> None:
    seen: list[str] = []

    @asynccontextmanager
    async def restart() -> AsyncGenerator[None]:
        seen.append("stop")
        yield
        seen.append("start")

    timeline = _with_laser_offset(opened.view.value.state.profiles["gfp"].timelines["ao_main"], "-2 ms")
    async with opened._scheduler.run("start a preview", requires=()):
        preview = await opened._scheduler.start(ActivityInfo(kind="preview"), {opened._active_profile}, restart=restart)
    await opened.set_generator_timeline("ao_main", timeline)
    assert seen == ["stop", "start"]

    await preview.end()
    async with opened._scheduler.run("start a capture", requires=()):
        await opened._scheduler.start(ActivityInfo(kind="capture"), {opened._store})
    with pytest.raises(ActivityBusyError):
        await opened.set_generator_timeline("ao_main", timeline)


async def test_a_wire_on_a_pin_the_generator_does_not_have_stops_the_opening(
    config_data: dict[str, Any], tmp_path: Path
) -> None:
    config_data["wiring"]["ao_main"]["galvo"]["pin"] = "ao99"
    microscope = _microscope(simulated(config_data), tmp_path)
    with pytest.raises(StartupError) as caught:
        await microscope.open()
    assert [(p.code, p.loc) for p in caught.value.problems] == [
        ("rig.wiring.unknown_pin", ("wiring", "ao_main", "galvo", "pin"))
    ]


@pytest.mark.parametrize("rig", [lambda data: data, sweep_x], ids=["the generator paces", "the stage paces"])
async def test_a_profile_loads_cycles_on_the_generators_own_clock(
    config_data: dict[str, Any], tmp_path: Path, rig: Any
) -> None:
    microscope = _microscope(simulated(rig(config_data)), tmp_path)
    await microscope.open()
    try:
        cycle = await microscope._hal.signal_generators["ao_main"].get_loaded()
        assert cycle is not None
        assert cycle.start == OwnClock()
    finally:
        await microscope.close()


async def _live(microscope: Microscope) -> dict[str, object]:
    """What a preview has started: each camera's mode, if the laser is on, the generator's state, the activities."""
    hal = microscope._hal
    return {
        "cameras": {uid: (await camera.props.get_value("mode")) for uid, camera in hal.cameras.items()},
        "laser": await hal.device("laser").props.get_value("is_on"),
        "generator": await hal.signal_generators["ao_main"].state.get(),
        "activities": [activity.kind for activity in microscope.view.value.activities],
    }


async def test_a_preview_starts_and_stops_its_devices(opened: Microscope) -> None:
    await opened.start_preview()
    assert await _live(opened) == {
        "cameras": {"camera": "PREVIEW"},
        "laser": True,
        "generator": "running",
        "activities": ["preview"],
    }
    await opened.stop_preview()
    assert await _live(opened) == {
        "cameras": {"camera": "IDLE"},
        "laser": False,
        "generator": "loaded",
        "activities": [],
    }


async def test_a_device_property_write_keeps_a_running_preview(opened: Microscope) -> None:
    await opened.start_preview()
    running = opened._preview

    await opened.set_device_properties("camera", {"exposure_time_ms": 20.0})

    assert opened._preview is running
    await opened.stop_preview()


async def test_a_laser_failsafe_during_a_preview_keeps_the_laser_off(opened: Microscope) -> None:
    await opened.start_preview()

    await opened.execute_device_command("laser", "off")

    live = await _live(opened)
    assert live["laser"] is False
    assert live["activities"] == ["preview"]
    await opened.stop_preview()


@pytest.mark.parametrize(
    ("device", "command"), [("camera", "capture_state"), ("x_axis", "halt")], ids=["query", "failsafe"]
)
async def test_a_query_or_failsafe_runs_while_another_command_holds_the_instrument(
    opened: Microscope, device: str, command: str
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


async def test_stop_ends_the_preview_and_runs_every_failsafe(opened: Microscope) -> None:
    await opened.start_preview()

    await opened.stop()

    live = await _live(opened)
    assert live["activities"] == []
    assert live["laser"] is False
    assert live["cameras"] == {"camera": "IDLE"}


async def test_a_preview_disarms_the_scan_axis(opened: Microscope) -> None:
    z = opened._hal.stage["z"]
    await z.arm_steps(1.0, 5, "ttl_in")
    await opened.start_preview()
    assert await z.scan_state.get() == "idle"
    await opened.stop_preview()


async def test_a_preview_restarts_around_a_profile_change(opened: Microscope) -> None:
    await opened.start_preview()
    await opened.select_profile("slow")
    assert (await _live(opened))["activities"] == ["preview"]
    assert await _exposure(opened) == pytest.approx(30.0)
    assert (await _live(opened))["cameras"] == {"camera": "PREVIEW"}
    await opened.stop_preview()


async def test_each_profile_keeps_its_preview_channels(config_data: dict[str, Any], tmp_path: Path) -> None:
    microscope = _microscope(two_cameras(simulated(config_data)), tmp_path)
    await microscope.open()
    try:
        await microscope.start_preview()
        assert microscope.view.value.preview_channels == ("camera",)
        await microscope.set_preview_channels(["camera_2"])
        assert (await _live(microscope))["cameras"] == {"camera": "IDLE", "camera_2": "PREVIEW"}
        await microscope.select_profile("rfp")
        assert microscope.view.value.preview_channels == ("camera",)
        await microscope.select_profile("gfp")
        assert microscope.view.value.preview_channels == ("camera_2",)
        assert (await _live(microscope))["cameras"] == {"camera": "IDLE", "camera_2": "PREVIEW"}
        with pytest.raises(RejectedError, match="no channel"):
            await microscope.set_preview_channels(["laser"])
    finally:
        await microscope.close()
