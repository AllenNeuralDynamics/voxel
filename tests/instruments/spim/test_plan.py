from pathlib import Path
from typing import Any

import pytest
from vxlib.vector import IVec2D, Vec2D

from vxl.devices.camera import CameraSensor
from vxl.instruments.spim.geometry import AxisRun
from vxl.instruments.spim.plan import Volume, plan_task
from vxl.instruments.spim.task import Task

from .support import load_file

_FILES = Path(__file__).parent / "files"
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
    """The volumes of 1 task over ``region``, with ``profiles`` of an example file."""
    example = load_file(_FILES / name)
    data = {"id": "t", "region": region, "profiles": list(profiles), **task}
    sensors = dict.fromkeys(example.config.optics.detectors(), sensor)
    return plan_task(Task.complete(data, example.default.task), example.config, example.default, sensors)


def test_exaspim_steps_z_and_its_side_selector_follows_x() -> None:
    sensor = _sensor(3.76, 14192, 10640)
    (left,) = _plan("exaspim-v1.yaml", sensor, _box([0, 100], x=(12000, 18000), y=(0, 9000)))
    (right,) = _plan("exaspim-v1.yaml", sensor, _box([0, 100], x=(37000, 43000), y=(0, 9000)))

    assert left.scan == AxisRun("z", 0.0, 1.0, 101)
    assert left.transforms["camera"].shape == (101, 10640, 14192)
    assert left.positions == {"excitation_side_selector": "left", "fw_emission": "BP525"}
    assert right.positions == {"excitation_side_selector": "right", "fw_emission": "BP525"}


def test_open_top_sweeps_x_one_slanted_frame_past_each_end() -> None:
    (volume,) = _plan("open-top.yaml", _sensor(6.5, 2048, 2048), _box([0, 500], x=(0, 1000), z=(0, 200)))
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
    volumes = _plan("exaspim-v1.yaml", _EXA, _box([0, 100], x=(0, 20000), y=(0, 15000)))
    # 3 tiles along X, 7200 µm apart (10 % overlap); 2 rows along Y; the X axis alternates, so row 2 runs back.
    assert _stops(volumes, "x", "y") == [
        ("gfp", "2799", "2697"),
        ("gfp", "10000", "2697"),
        ("gfp", "17201", "2697"),
        ("gfp", "17201", "12303"),
        ("gfp", "10000", "12303"),
        ("gfp", "2799", "12303"),
    ]


def test_tiles_that_miss_the_region_are_left_out() -> None:
    triangle = {"kind": "convex_hull", "points": [{"x": 0, "y": 0}, {"x": 20000, "y": 0}, {"x": 0, "y": 15000}]}
    volumes = _plan("exaspim-v1.yaml", _EXA, {"outline": triangle, "bounds": [0, 100]})
    assert ("gfp", "17201", "12303") not in _stops(volumes, "x", "y")
    assert len(volumes) == 5


def test_explicit_points_place_1_volume_on_each() -> None:
    points = {"kind": "explicit_points", "points": [{"x": 0, "y": 0}, {"x": 5000, "y": 9000}]}
    volumes = _plan("exaspim-v1.yaml", _EXA, {"outline": points, "bounds": [0, 100]})
    assert _stops(volumes, "x", "y") == [("gfp", "0", "0"), ("gfp", "5000", "9000")]


def test_a_region_drawn_from_the_side_tiles_y_and_z_and_every_stop_sweeps_the_same_x() -> None:
    side = {"kind": "convex_hull", "points": [{"x": 0, "z": 0}, {"x": 3000, "z": 0}, {"x": 1500, "z": 1200}]}
    volumes = _plan("open-top.yaml", _sensor(6.5, 2048, 2048), {"outline": side, "bounds": [0, 1500]})
    assert _stops(volumes, "y", "z") == [
        ("gfp", "391", "121"),
        ("gfp", "1109", "121"),
        ("gfp", "1109", "600"),
        ("gfp", "391", "600"),
        ("gfp", "391", "1079"),
        ("gfp", "1109", "1079"),
    ]
    assert {v.scan for v in volumes} == {volumes[0].scan}


def test_profile_major_runs_every_stop_of_1_profile_before_the_next() -> None:
    region = _box([0, 1500], x=(0, 1000), z=(0, 200))
    volumes = _plan("open-top.yaml", _sensor(6.5, 2048, 2048), region, ("gfp", "cy5"), iteration="profile_major")
    assert [v.profile for v in volumes] == ["gfp", "gfp", "cy5", "cy5"]
