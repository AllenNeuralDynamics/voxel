from collections.abc import Callable
from typing import Any

import pytest
from vxl_instruments.spim.plan import PlannedTask, Planner, Unplanned, Volume
from vxl_instruments.spim.task import SPIMTask
from vxlib.vector import IVec2D, Vec2D

from vxl._utils.files import load_yaml
from vxl.devices.camera import CameraSensor
from vxl.instrument.geometry import AxisRun

from .support import TEMPLATES, Example, load, load_file

SLANT = 281.83
"""Half of what 1 open-top frame sees along X, in µm: its slanted sheet reaches about 565 µm along X."""


def _sensor(pixel: float, x: int, y: int) -> CameraSensor:
    return CameraSensor(pixel_um=Vec2D(x=pixel, y=pixel), size_px=IVec2D(x=x, y=y))


def _box(bounds: list[float], **axes: tuple[float, float]) -> dict[str, Any]:
    """A region: a box on 2 named axes, and ``bounds`` on the third."""
    (a, (a0, a1)), (b, (b0, b1)) = axes.items()
    return {"outline": {"kind": "bounding_box", "points": [{a: a0, b: b0}, {a: a1, b: b1}]}, "bounds": bounds}


def _plan(
    name: str, sensor: CameraSensor, region: dict[str, Any], profiles: tuple[str, ...] = ("gfp",), **task: Any
) -> list[Volume]:
    """The volumes of 1 task over ``region``, with ``profiles`` of a shipped template."""
    example = load_file(TEMPLATES / name)
    data = {"id": "t", "region": region, "profiles": list(profiles), **task}
    sensors = dict.fromkeys(example.config.optics.detectors(), sensor)
    state = example.default.model_copy(update={"plan": [SPIMTask.complete(data, example.default.task)]})
    plans = Planner(example.config, state, sensors).plan()
    assert plans.fingerprint is not None, plans.tasks
    return list(plans.volumes)


def test_exaspim_steps_z_and_its_side_selector_follows_x() -> None:
    sensor = _sensor(3.76, 14192, 10640)
    (left,) = _plan("z-step.yaml", sensor, _box([0, 100], x=(12000, 18000), y=(0, 9000)))
    (right,) = _plan("z-step.yaml", sensor, _box([0, 100], x=(37000, 43000), y=(0, 9000)))

    assert left.scan == AxisRun("z", 0.0, 1.0, 101)
    assert left.transforms["camera"].shape == (101, 10640, 14192)
    assert left.positions == {"excitation_side_selector": "left", "fw_emission": "BP525"}
    assert right.positions == {"excitation_side_selector": "right", "fw_emission": "BP525"}


def test_open_top_sweeps_x_one_slanted_frame_past_each_end() -> None:
    (volume,) = _plan("x-sweep-oblique.yaml", _sensor(6.5, 2048, 2048), _box([0, 500], x=(0, 1000), z=(0, 200)))
    run = volume.scan
    last = run.first + run.spacing * (run.count - 1)
    assert (run.axis, run.spacing) == ("x", 0.5)
    assert run.speed == pytest.approx(0.5 / 0.010 * 0.95)
    assert run.first == pytest.approx(-SLANT, abs=0.01)
    assert last == pytest.approx(1000 + SLANT, abs=run.spacing)
    assert volume.transforms["camera"].shape == (run.count, 2048, 2048)


def _stops(volumes: list[Volume], *axes: str) -> list[tuple[str, ...]]:
    """Each volume's profile and its stage start on ``axes``, rounded to whole µm."""
    return [(v.profile, *(str(round(getattr(v.start, axis))) for axis in axes)) for v in volumes]


_EXA = _sensor(3.76, 14192, 10640)
"""The exaSPIM camera: with the rig's optics, 1 frame sees about 8000 µm along X and 10700 µm along Y."""


def test_tiles_cover_the_region_with_overlap_and_snake_back() -> None:
    volumes = _plan("z-step.yaml", _EXA, _box([0, 100], x=(0, 20000), y=(0, 15000)))
    # 3 tiles along X, 7200 µm apart (10 % overlap); 2 rows along Y; the X axis alternates, so row 2 runs back.
    assert _stops(volumes, "x", "y") == [
        ("gfp", "2799", "2697"),
        ("gfp", "10000", "2697"),
        ("gfp", "17201", "2697"),
        ("gfp", "17201", "12303"),
        ("gfp", "10000", "12303"),
        ("gfp", "2799", "12303"),
    ]


def test_a_grid_that_starts_at_the_high_corner_runs_from_there_and_snakes_back() -> None:
    tiles = {"kind": "grid", "axes": [{"x": "alternate"}, {"y": "forward"}], "start": {"x": "high", "y": "high"}}
    path = {"scan": {"z": "forward"}, "tiles": tiles}
    volumes = _plan("z-step.yaml", _EXA, _box([0, 100], x=(0, 20000), y=(0, 15000)), path=path)
    assert _stops(volumes, "x", "y") == [
        ("gfp", "17201", "12303"),
        ("gfp", "10000", "12303"),
        ("gfp", "2799", "12303"),
        ("gfp", "2799", "2697"),
        ("gfp", "10000", "2697"),
        ("gfp", "17201", "2697"),
    ]


def test_tiles_that_miss_the_region_are_left_out() -> None:
    triangle = {"kind": "convex_hull", "points": [{"x": 0, "y": 0}, {"x": 20000, "y": 0}, {"x": 0, "y": 15000}]}
    volumes = _plan("z-step.yaml", _EXA, {"outline": triangle, "bounds": [0, 100]})
    assert ("gfp", "17201", "12303") not in _stops(volumes, "x", "y")
    assert len(volumes) == 5


def test_explicit_points_place_1_volume_on_each() -> None:
    points = {"kind": "explicit_points", "points": [{"x": 0, "y": 0}, {"x": 5000, "y": 9000}]}
    volumes = _plan("z-step.yaml", _EXA, {"outline": points, "bounds": [0, 100]})
    assert _stops(volumes, "x", "y") == [("gfp", "0", "0"), ("gfp", "5000", "9000")]


def test_a_region_drawn_from_the_side_tiles_y_and_z_and_every_stop_sweeps_the_same_x_back_and_forth() -> None:
    side = {"kind": "convex_hull", "points": [{"x": 0, "z": 0}, {"x": 3000, "z": 0}, {"x": 1500, "z": 1200}]}
    volumes = _plan("x-sweep-oblique.yaml", _sensor(6.5, 2048, 2048), {"outline": side, "bounds": [0, 1500]})
    assert _stops(volumes, "y", "z") == [
        ("gfp", "391", "121"),
        ("gfp", "1109", "121"),
        ("gfp", "1109", "600"),
        ("gfp", "391", "600"),
        ("gfp", "391", "1079"),
        ("gfp", "1109", "1079"),
    ]
    assert {_frames(v.scan) for v in volumes} == {_frames(volumes[0].scan)}  # the template's X alternates
    assert [v.scan.spacing > 0 for v in volumes] == [True, False, True, False, True, False]
    assert all(v.start.x == v.scan.first for v in volumes)


def _frames(run: AxisRun) -> tuple[float, ...]:
    """The frame positions a run covers, low to high, rounded to 0.01 µm."""
    return tuple(sorted(round(run.first + run.spacing * i, 2) for i in range(run.count)))


def test_a_forward_scan_runs_every_stop_from_the_low_end() -> None:
    volumes = _plan("z-step.yaml", _EXA, _box([0, 100], x=(0, 20000), y=(0, 15000)))
    assert {v.scan for v in volumes} == {AxisRun("z", 0.0, 1.0, 101)}


def test_profile_major_runs_every_stop_of_1_profile_before_the_next() -> None:
    region = _box([0, 1500], x=(0, 1000), z=(0, 200))
    volumes = _plan("x-sweep-oblique.yaml", _sensor(6.5, 2048, 2048), region, ("gfp", "cy5"), iteration="profile_major")
    assert [v.profile for v in volumes] == ["gfp", "gfp", "cy5", "cy5"]


def _edited(name: str, edit: Callable[[dict[str, Any]], None]) -> Example:
    """A shipped template after ``edit`` changes its file."""
    found = load_yaml(TEMPLATES / name)
    edit(found)
    return load({"id": "5x8k2m9q4r7t1v3w6y0z2b4c8d", "name": "example", **found["rig"], "default": found["default"]})


def _planner(example: Example, sensor: CameraSensor, tasks: dict[str, tuple[dict[str, Any], list[str]]]) -> Planner:
    """A planner for ``tasks``, each a region and its profiles, with every camera on ``sensor``."""
    plan = [
        SPIMTask.complete({"id": task_id, "region": region, "profiles": profiles}, example.default.task)
        for task_id, (region, profiles) in tasks.items()
    ]
    state = example.default.model_copy(update={"plan": plan})
    return Planner(example.config, state, dict.fromkeys(example.config.optics.detectors(), sensor))


def _zoom(data: dict[str, Any]) -> None:
    """A zoom changer of 1 or 2 times after the objective, that follows the stage along X: 1 times below 0 µm."""
    rig = data["rig"]
    rig["parts"]["zoom_1x"] = {"target": "vxl.parts.Objective", "magnification": 1.0}
    rig["parts"]["zoom_2x"] = {"target": "vxl.parts.Objective", "magnification": 2.0}
    rig["devices"]["zoom"] = {
        "target": "vxl.devices.axes.simulated.SimulatedDiscreteAxis",
        "init": {"slots": {"0": "zoom_1x", "1": "zoom_2x"}},
    }
    after = rig["optics"]["objective"]["to"]
    rig["optics"]["objective"] = {"to": "zoom"}
    rig["optics"]["zoom"] = {"to": after}
    data["default"]["positions"]["zoom"] = {"axis": "x", "order": ["zoom_1x", "zoom_2x"], "at": [0], "margin": 100}


def test_a_device_that_follows_the_stage_makes_zones_and_each_stop_names_its_zone() -> None:
    planner = _planner(
        load_file(TEMPLATES / "z-step.yaml"), _EXA, {"t": (_box([0, 100], x=(0, 40000), y=(0, 9000)), ["gfp"])}
    )
    plans = planner.plan()
    planned = plans.tasks["t"]
    assert isinstance(planned, PlannedTask)
    (only,) = plans.footprints  # the side of the light does not move the picture
    assert len(only) == 8
    assert [zone.devices for zone in planned.zones] == [
        {"excitation_side_selector": "left"},
        {"excitation_side_selector": "right"},
    ]
    assert all(zone.cameras == {"gfp": {"camera": only}} for zone in planned.zones)
    xs = planned.axis_values_um["x"]
    assert [planned.zones[zone].devices["excitation_side_selector"] for _, _, zone in planned.stops] == [
        "left" if xs[i] < 20000 else "right" for i, _, _ in planned.stops
    ]


def test_a_zoom_that_follows_the_stage_spaces_the_stops_by_its_smaller_footprint() -> None:
    example = _edited("z-step.yaml", _zoom)
    planner = _planner(example, _EXA, {"t": (_box([0, 100], x=(-12000, 12000), y=(0, 9000)), ["gfp"])})
    plans = planner.plan()
    planned = plans.tasks["t"]
    assert isinstance(planned, PlannedTask)
    assert [zone.devices["zoom"] for zone in planned.zones] == ["zoom_1x", "zoom_2x"]
    wide, narrow = (zone.cameras["gfp"]["camera"] for zone in planned.zones)
    assert sorted(plans.footprints) == sorted({wide, narrow})
    assert planned.overlap[narrow]["x"] == pytest.approx(0.1)  # the task's overlap
    assert planned.overlap[wide]["x"] == pytest.approx(0.55)  # twice as wide: more overlap, no gap


def test_cameras_of_1_profile_with_different_regions_space_the_stops_by_the_smallest() -> None:
    def shift(data: dict[str, Any]) -> None:
        data["default"]["profiles"]["round_1"]["fov"] = {"cam_4": {"x": 1000, "y": 600, "w": 2000, "h": 1000}}

    example = _edited("z-step-4-cameras.yaml", shift)
    region = _box([0, 10], x=(0, 20000), y=(0, 20000))
    plans = _planner(example, _sensor(6.5, 4096, 4096), {"t": (region, ["round_1"])}).plan()
    planned = plans.tasks["t"]
    assert isinstance(planned, PlannedTask)
    overlap = {plans.footprints[f].camera: value for f, value in planned.overlap.items()}
    assert sorted(overlap) == ["cam_1", "cam_2", "cam_3", "cam_4"]
    assert overlap["cam_4"] == pytest.approx({"x": 0.1, "y": 0.1})
    assert all(overlap[camera]["x"] > 0.1 for camera in ("cam_1", "cam_2", "cam_3"))


def test_a_task_that_cannot_be_planned_holds_its_reason_and_the_others_are_planned() -> None:
    example = load_file(TEMPLATES / "z-step-4-cameras.yaml")
    region = _box([0, 10], x=(0, 1000), y=(0, 1000))
    sensors: dict[str, CameraSensor] = dict.fromkeys(("cam_1", "cam_2", "cam_3"), _sensor(6.5, 2048, 2048))
    plan = [
        SPIMTask.complete({"id": task_id, "region": region, "profiles": [profile]}, example.default.task)
        for task_id, profile in (("all", "round_1"), ("two", "round_3"))
    ]
    state = example.default.model_copy(update={"plan": plan})
    plans = Planner(example.config, state, sensors).plan()
    assert plans.tasks["all"] == Unplanned(code="task.plan.sensor_missing", msg="cam_4 has not reported its sensor.")
    assert isinstance(plans.tasks["two"], PlannedTask)
    assert sorted(f.camera for f in plans.footprints.values()) == ["cam_1", "cam_2"]
    assert {v.task for v in plans.volumes} == {"two"}
    assert plans.fingerprint is None


def test_any_failure_while_planning_a_task_leaves_it_unplanned() -> None:
    example = load_file(TEMPLATES / "z-step.yaml")
    gfp = example.default.profiles["gfp"]
    profile = gfp.model_copy(update={"props": {**gfp.props, "camera": {**gfp.props.get("camera", {}), "binning": 2.0}}})
    example = Example(example.config, example.default.model_copy(update={"profiles": {"gfp": profile}}))
    plans = _planner(example, _EXA, {"t": (_box([0, 100], x=(0, 20000), y=(0, 15000)), ["gfp"])}).plan()
    assert plans.tasks["t"] == Unplanned(code="task.plan.failed", msg="binning must be a whole number, got 2.0")
    assert plans.fingerprint is None


def test_the_same_plan_gives_the_same_fingerprint_and_a_change_gives_another() -> None:
    example = load_file(TEMPLATES / "z-step.yaml")
    tasks = {"t": (_box([0, 100], x=(0, 20000), y=(0, 15000)), ["gfp"])}
    first = _planner(example, _EXA, tasks).plan().fingerprint
    assert _planner(example, _EXA, tasks).plan().fingerprint == first
    assert first is not None
    assert len(first) == 12
    smaller = _sensor(3.76, 14192, 10000)
    assert _planner(example, smaller, tasks).plan().fingerprint != first
