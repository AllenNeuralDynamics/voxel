from typing import Any

import pytest
from pydantic import ValidationError

from vxl.instruments.spim.state import SPIMState
from vxl.instruments.spim.task import (
    Region,
    SPIMTask,
)

from .support import load, sweep_x

_REGION = {
    "outline": {"kind": "convex_hull", "points": [{"x": 0, "y": 0}, {"x": 8000, "y": 500}, {"x": 7000, "y": 6000}]},
    "bounds": [0, 3000],
}


def _preset(config_data: dict[str, Any], *tasks: dict[str, Any]) -> SPIMState:
    default = load(config_data).default
    plan = [SPIMTask.complete(task, default.task) for task in tasks]
    return SPIMState.model_validate({**default.model_dump(mode="json"), "plan": plan})


def _codes(config_data: dict[str, Any], *tasks: dict[str, Any]) -> list[str]:
    preset, example = _preset(config_data, *tasks), load(config_data)
    return [v.code or "" for v in preset.problems(example.config)]


def test_a_short_task_takes_the_instrument_defaults(config_data: dict[str, Any]) -> None:
    task = _preset(config_data, {"id": "brain", "region": _REGION, "profiles": ["gfp"]}).plan[0]
    assert str(task.overlap["x"]) == "10 %"
    assert task.path.scan == {"z": "forward"}
    assert task.model_dump(mode="json")["path"]["tiles"] == {
        "kind": "grid",
        "axes": [{"x": "alternate"}, {"y": "forward"}],
    }


def test_example_plan_has_no_problems(config_data: dict[str, Any]) -> None:
    task = {"id": "brain", "region": _REGION, "profiles": ["gfp"]}
    assert _codes(config_data, task) == []
    assert _codes(sweep_x(config_data), task) == []


@pytest.mark.parametrize(
    ("points", "across", "along"),
    [([{"x": 0, "y": 0}, {"x": 1, "y": 1}], ("x", "y"), "z"), ([{"z": 0, "x": 0}, {"z": 1, "x": 1}], ("x", "z"), "y")],
)
def test_a_region_names_its_own_axes(points: list[dict[str, float]], across: tuple[str, str], along: str) -> None:
    region = Region.model_validate({"outline": {"kind": "bounding_box", "points": points}, "bounds": [0, 1]})
    assert (region.across, region.along) == (across, along)


@pytest.mark.parametrize(
    ("outline", "match"),
    [
        ({"kind": "bounding_box", "points": [{"x": 0, "y": 0}, {"x": 1, "z": 1}]}, "the same 2 stage axes"),
        ({"kind": "bounding_box", "points": [{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 1, "z": 1}]}, "the same 2"),
        ({"kind": "bounding_box", "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]}, "span both axes"),
        ({"kind": "convex_hull", "points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}, {"x": 2, "y": 2}]}, "1 line"),
        ({"kind": "explicit_points", "points": [{"x": 0, "y": 0}, {"x": 0, "y": 0}]}, "must be unique"),
    ],
)
def test_outline_rules(outline: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Region.model_validate({"outline": outline, "bounds": [0, 1]})


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"overlap": {"x": "10 %"}}, "task.overlap.missing"),
        ({"overlap": {"x": "10 %", "y": "10 %", "z": "10 %"}}, "task.overlap.unexpected"),
        ({"path": {"scan": {"x": "forward"}, "tiles": {"kind": "nearest_neighbor"}}}, "task.path.scan.missing"),
        (
            {"path": {"scan": {"z": "forward"}, "tiles": {"kind": "grid", "axes": [{"x": "alternate"}]}}},
            "task.path.grid_axes",
        ),
        (
            {
                "path": {
                    "scan": {"z": "forward"},
                    "tiles": {"kind": "grid", "axes": [{"x": "forward"}, {"y": "alternate"}]},
                }
            },
            "task.path.slowest_alternate",
        ),
        ({"path": {"scan": {"z": "forward"}, "tiles": {"kind": "as_given"}}}, "task.path.as_given_needs_points"),
        ({"profiles": ["missing"]}, "task.profile_missing"),
    ],
)
def test_task_axes_must_match_the_instrument(config_data: dict[str, Any], change: dict[str, Any], code: str) -> None:
    assert code in _codes(config_data, {"id": "t", "region": _REGION, "profiles": ["gfp"], **change})


@pytest.mark.parametrize(("point", "untiled"), [({"x": 0, "y": 0}, True), ({"y": 0, "z": 0}, False)])
def test_explicit_points_must_name_the_tiled_axes(
    config_data: dict[str, Any], point: dict[str, float], untiled: bool
) -> None:
    sweep_x(config_data)
    config_data["default"]["task"]["path"]["tiles"] = {"kind": "as_given"}
    region = {"outline": {"kind": "explicit_points", "points": [point]}, "bounds": [0, 1]}
    codes = _codes(config_data, {"id": "points", "region": region, "profiles": ["gfp"]})
    assert ("task.region.explicit_points_untiled" in codes) is untiled


def test_task_ids_are_unique(config_data: dict[str, Any]) -> None:
    task = {"id": "same", "region": _REGION, "profiles": ["gfp"]}
    with pytest.raises(ValidationError, match="task ids must be unique"):
        _preset(config_data, task, task)


@pytest.mark.parametrize(("specimen", "outside"), [([-1000, 9000], False), ([0, 5000], True)])
def test_a_region_stays_inside_the_specimen_range(
    config_data: dict[str, Any], specimen: list[float], outside: bool
) -> None:
    config_data["stage"]["x"]["specimen"] = specimen
    codes = _codes(config_data, {"id": "brain", "region": _REGION, "profiles": ["gfp"]})
    assert ("task.region.outside_specimen" in codes) is outside


def test_a_specimen_range_needs_2_different_numbers(config_data: dict[str, Any]) -> None:
    config_data["stage"]["x"]["specimen"] = [5, 5]
    with pytest.raises(ValidationError, match="2 different numbers"):
        load(config_data)
