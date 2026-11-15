import copy
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from .support import bench

type Change = Callable[[dict[str, Any]], Any]

_DIGITAL = {"kind": "digital", "off": "0 V", "on": "5 V"}

_HAL: dict[str, Any] = {
    "parts": {
        "galvo": {"kind": "galvo"},
        "objective": {"target": "vxl.parts.Objective", "magnification": 5},
        "GFP": {"target": "vxl.parts.Filter", "band": ["500 nm", "550 nm"]},
        "RFP": {"target": "vxl.parts.Filter", "band": ["575 nm", None]},
    },
    "devices": {
        **{uid: {"target": "builtins.object"} for uid in ("ao_main", "camera", "laser", "x_axis", "y_axis", "z_axis")},
        "fw": {"target": "builtins.object", "init": {"slots": {"0": "GFP", "1": "RFP"}}},
    },
    "wiring": {
        "ao_main": {
            "camera_trigger": {"pin": "ao0", "to": ["camera/trigger_in"], **_DIGITAL},
            "laser": {"pin": "ao1", "to": ["laser/enable_in"], **_DIGITAL},
            "galvo": {"pin": "ao2", "to": ["galvo/in"], "kind": "analog", "limits": {"V": [-1, 1]}, "park": "0 V"},
        },
    },
    "optics": {
        "laser": {"to": "galvo"},
        "galvo": {"to": "sample"},
        "sample": {"to": "objective"},
        "objective": {"to": "fw"},
        "fw": {"to": "camera"},
        "camera": {"width": {"y": 1}, "height": {"x": -1}},
    },
    "stage": {"x": "x_axis", "y": "y_axis", "z": "z_axis"},
}


def _codes(data: dict[str, Any]) -> list[str]:
    return bench(data).problems().codes()


def test_the_bench_alone_has_no_problems() -> None:
    hal = bench(_HAL)
    assert hal.problems() == []
    assert bench(hal.model_dump(mode="json")) == hal


def test_the_bench_says_nothing_about_a_capture() -> None:
    with pytest.raises(ValidationError, match=r"scan\s+Extra inputs are not permitted"):
        bench({**_HAL, "scan": {"axis": "z", "motion": "step", "pacer": "ao_main"}})


def _wires(data: dict[str, Any]) -> dict[str, Any]:
    return data["wiring"]["ao_main"]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda d: _wires(d)["laser"].update(to=["camera/trigger_in"]), "rig.wiring.pin_shared"),
        (lambda d: d["wiring"].update(galvo={}), "rig.wiring.device_missing"),
        (lambda d: _wires(d)["galvo"].update(to=["galvoo/in"]), "rig.wiring.receiver_missing"),
        (
            lambda d: d["parts"].update(sample={"kind": "spot"}),
            "rig.reserved_name",
        ),
        (lambda d: d["stage"].update(x="x_axiss"), "rig.stage.device_missing"),
        (lambda d: d["optics"]["sample"].update(to="fw_emision"), "rig.optics.target_missing"),
        (lambda d: d["parts"].pop("galvo"), "rig.optics.node_unknown"),
        (lambda d: d["optics"].pop("sample"), "rig.optics.sample_missing"),
        (lambda d: d["optics"]["fw"].update(to={"GFP": "camra"}), "rig.optics.target_missing"),
    ],
)
def test_bench_problems(change: Change, code: str) -> None:
    data = copy.deepcopy(_HAL)
    change(data)
    assert code in _codes(data)


@pytest.mark.parametrize(
    ("part", "match"),
    [
        ({"target": "vxl.parts.Filter"}, r"band\s+Field required"),
        ({"target": "vxl.parts.Filter", "band": ["550 nm", "500 nm"]}, "from low to high"),
        ({"target": "vxl.parts.Filter", "band": [500, 550]}, "number and a unit"),
        ({"target": "vxl.parts.Objective"}, r"magnification\s+Field required"),
        ({"kind": "galvo", "band": ["500 nm", "550 nm"]}, r"band\s+Extra inputs"),
        ({"target": "vxl.parts.Fliter", "band": ["500 nm", "550 nm"]}, "has no 'Fliter'"),
        ({"target": "builtins.object"}, "not a subclass of Part"),
    ],
)
def test_the_class_of_a_part_checks_its_values_when_the_file_is_read(part: dict[str, Any], match: str) -> None:
    data = copy.deepcopy(_HAL)
    data["parts"]["new_part"] = part
    with pytest.raises(ValidationError, match=match) as caught:
        bench(data)
    assert caught.value.errors()[0]["loc"][:2] == ("parts", "new_part")


def test_a_part_and_a_device_cannot_share_a_name() -> None:
    data = copy.deepcopy(_HAL)
    data["parts"]["camera"] = {"kind": "spot"}
    with pytest.raises(ValidationError, match="Component UID 'camera' is duplicated"):
        bench(data)


def test_each_side_of_the_sample_takes_its_numbers_from_its_own_parts() -> None:
    data = copy.deepcopy(_HAL)
    data["parts"]["excitation_objective"] = {"target": "vxl.parts.Objective", "magnification": 10}
    data["optics"]["galvo"]["to"] = "excitation_objective"
    data["optics"]["excitation_objective"] = {"to": "sample"}
    hal = bench(data)
    assert hal.problems() == []
    assert [type(part).__name__ for part in hal.parts.values()] == [
        "Part",
        "Objective",
        "Filter",
        "Filter",
        "Objective",
    ]

    gfp = {"fw": "GFP"}
    (lit,) = hal.optics.paths_from("laser", {})
    assert lit.nodes == ("laser", "galvo", "excitation_objective", "sample")
    assert (hal.magnification(lit, gfp), hal.band(lit, gfp)) == (10, None)

    (seen,) = hal.optics.paths_to("camera", {})
    assert seen.nodes == ("sample", "objective", "fw", "camera")
    assert (hal.magnification(seen, gfp), hal.band(seen, gfp)) == (5, (500, 550))
    assert hal.band(seen, {"fw": "RFP"}) == (575, None)


def test_a_device_with_no_position_given_holds_no_part() -> None:
    hal = bench(_HAL)
    (path,) = hal.optics.paths_to("camera", {})
    assert (hal.magnification(path, {}), hal.band(path, {})) == (5, None)
