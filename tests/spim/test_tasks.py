from typing import Any

import pytest
from pydantic import ValidationError

from vxl.spim.config import InstrumentPreset, Surface, Task

from .support import load, sweep_x

_REGION = {
    "xy": {"kind": "convex_hull", "points": [{"x": 0, "y": 0}, {"x": 8000, "y": 500}, {"x": 7000, "y": 6000}]},
    "z": {"start": 0, "end": 3000},
}


def _preset(config_data: dict[str, Any], *tasks: dict[str, Any]) -> InstrumentPreset:
    config = load(config_data)
    plan = [Task.complete(task, config.default.task) for task in tasks]
    return InstrumentPreset.model_validate({**config.default.model_dump(mode="json"), "plan": plan})


def _codes(config_data: dict[str, Any], *tasks: dict[str, Any]) -> list[str]:
    preset, config = _preset(config_data, *tasks), load(config_data)
    return [v.code or "" for v in preset.violations(config.hal)]


def test_a_short_task_takes_the_instrument_defaults(config_data: dict[str, Any]) -> None:
    task = _preset(config_data, {"id": "brain", "region": _REGION, "profiles": ["gfp"]}).plan[0]
    assert str(task.overlap["x"]) == "10 %"
    assert task.path.scan == {"z": "forward"}
    assert task.model_dump(mode="json")["path"]["tiles"] == {
        "kind": "grid",
        "axes": [{"x": "alternate"}, {"y": "forward"}],
    }


def test_example_plan_has_no_violations(config_data: dict[str, Any]) -> None:
    task = {"id": "brain", "region": _REGION, "profiles": ["gfp"]}
    assert _codes(config_data, task) == []
    assert _codes(sweep_x(config_data), task) == []


def test_z_bounds_can_be_surfaces() -> None:
    task = Task.model_validate(
        {
            "id": "uneven",
            "region": {
                "xy": {"kind": "bounding_box", "points": [{"x": 0, "y": 0}, {"x": 6000, "y": 4000}]},
                "z": {
                    "start": {
                        "points": [
                            {"x": 0, "y": 0, "z": 0},
                            {"x": 6000, "y": 0, "z": 200},
                            {"x": 0, "y": 4000, "z": 100},
                        ]
                    },
                    "end": 3000,
                },
            },
            "profiles": ["gfp"],
            "overlap": {},
            "path": {"scan": {}, "tiles": {"kind": "nearest_neighbor"}},
            "iteration": "position_major",
        }
    )
    assert isinstance(task.region.z.start, Surface)
    assert task.region.z.end == 3000


@pytest.mark.parametrize(
    ("z", "match"),
    [
        ({"start": 3000, "end": 0}, "must be below"),
        (
            {
                "start": {"points": [{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 1, "z": 0}, {"x": 2, "y": 2, "z": 0}]},
                "end": 1,
            },
            "1 line",
        ),
    ],
)
def test_z_bound_rules(z: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Task.model_validate(
            {
                "id": "t",
                "region": {"xy": _REGION["xy"], "z": z},
                "profiles": ["gfp"],
                "overlap": {},
                "path": {"scan": {}, "tiles": {"kind": "optimized"}},
                "iteration": "position_major",
            }
        )


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


def test_explicit_points_need_x_and_y_tiled(config_data: dict[str, Any]) -> None:
    sweep_x(config_data)
    config_data["default"]["task"]["path"]["tiles"] = {"kind": "as_given"}
    task = {
        "id": "points",
        "region": {"xy": {"kind": "explicit_points", "points": [{"x": 0, "y": 0}]}, "z": {"start": 0, "end": 1}},
    }
    assert "task.region.explicit_points_untiled" in _codes(config_data, {**task, "profiles": ["gfp"]})


def test_task_ids_are_unique(config_data: dict[str, Any]) -> None:
    task = {"id": "same", "region": _REGION, "profiles": ["gfp"]}
    with pytest.raises(ValidationError, match="task ids must be unique"):
        _preset(config_data, task, task)
