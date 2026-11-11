import copy
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from vxl.hal_next.config import HALConfig

type Change = Callable[[dict[str, Any]], Any]

_DIGITAL = {"kind": "digital", "off": "0 V", "on": "5 V"}

_HAL: dict[str, Any] = {
    "devices": {
        **{uid: {"target": "builtins.object"} for uid in ("ao_main", "camera", "laser", "x_axis", "y_axis", "z_axis")},
        "fw": {"target": "builtins.object", "init": {"slots": {"0": "GFP", "1": "RFP"}}},
    },
    "parts": {
        "galvo": {"kind": "galvo"},
        "objective": {"kind": "objective", "magnification": 5},
        "GFP": {"kind": "filter", "band": ["500 nm", "550 nm"]},
        "RFP": {"kind": "filter", "band": ["575 nm", None]},
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
    return [violation.code or "" for violation in HALConfig.model_validate(data).violations()]


def test_the_bench_alone_has_no_problems() -> None:
    hal = HALConfig.model_validate(_HAL)
    assert hal.violations() == []
    assert hal.generators() == {"ao_main"}
    assert HALConfig.model_validate(hal.model_dump(mode="json")) == hal


def test_the_bench_says_nothing_about_a_capture() -> None:
    with pytest.raises(ValidationError, match=r"scan\s+Extra inputs are not permitted"):
        HALConfig.model_validate({**_HAL, "scan": {"axis": "z", "motion": "step", "pacer": "ao_main"}})


def _wires(data: dict[str, Any]) -> dict[str, Any]:
    return data["wiring"]["ao_main"]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda d: _wires(d)["laser"].update(to=["camera/trigger_in"]), "hal.wiring.pin_shared"),
        (lambda d: d["wiring"].update(galvo={}), "hal.wiring.device_missing"),
        (lambda d: _wires(d)["galvo"].update(to=["galvoo/in"]), "hal.wiring.receiver_missing"),
        (lambda d: d["parts"].update(camera={}), "hal.parts.device_name"),
        (lambda d: d["parts"].update(spare_lens={}), "hal.parts.unused"),
        (lambda d: d["parts"].update(sample={}), "hal.reserved_name"),
        (lambda d: d["stage"].update(x="x_axiss"), "hal.stage.device_missing"),
        (lambda d: d["optics"]["sample"].update(to="fw_emision"), "hal.optics.target_missing"),
        (lambda d: d["parts"].pop("galvo"), "hal.optics.node_unknown"),
        (lambda d: d["optics"].pop("sample"), "hal.optics.sample_missing"),
        (lambda d: d["optics"]["galvo"].update(to={"a": "sample"}), "hal.optics.positions_missing"),
        (lambda d: d["optics"]["laser"].update(to={"on": "galvo"}), "hal.optics.positions_missing"),
        (lambda d: d["optics"]["fw"].update(to={"GFP": "camera", "YFP": "camera"}), "hal.optics.position_unknown"),
        (lambda d: d["optics"]["fw"].update(to={"GFP": "camra"}), "hal.optics.target_missing"),
        (lambda d: d["devices"]["fw"]["init"]["slots"].update({"2": "525/50"}), "hal.devices.slot_label"),
        (lambda d: d["parts"].update(GFPP=d["parts"].pop("GFP")), "hal.parts.unused"),
        (lambda d: d["parts"].update(objective={"kind": "lens"}), "hal.optics.magnification_missing"),
    ],
)
def test_bench_problems(change: Change, code: str) -> None:
    data = copy.deepcopy(_HAL)
    change(data)
    assert code in _codes(data)


@pytest.mark.parametrize(
    ("part", "match"),
    [
        ({"kind": "filter"}, r"band\s+Field required"),
        ({"kind": "filter", "band": ["550 nm", "500 nm"]}, "from low to high"),
        ({"kind": "filter", "band": [500, 550]}, "number and a unit"),
        ({"kind": "objective"}, r"magnification\s+Field required"),
        ({"kind": "galvo", "band": ["500 nm", "550 nm"]}, r"band\s+Extra inputs are not permitted"),
        ({"kind": "fliter", "band": ["500 nm", "550 nm"]}, r"band\s+Extra inputs are not permitted"),
    ],
)
def test_kind_picks_the_class_of_a_part(part: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        HALConfig.model_validate({**_HAL, "parts": {**_HAL["parts"], "new_part": part}})


def test_a_path_takes_its_numbers_from_the_parts_after_the_sample() -> None:
    data = copy.deepcopy(_HAL)
    data["parts"]["excitation_objective"] = {"kind": "objective", "magnification": 10}
    data["optics"]["galvo"]["to"] = "excitation_objective"
    data["optics"]["excitation_objective"] = {"to": "sample"}
    hal = HALConfig.model_validate(data)
    assert hal.violations() == []
    assert [type(part).__name__ for part in hal.parts.values()] == [
        "Part",
        "Objective",
        "Filter",
        "Filter",
        "Objective",
    ]

    by_position = {path.positions["fw"]: path for path in hal.light_paths("laser", "camera")}
    assert by_position["GFP"].nodes == ("laser", "galvo", "excitation_objective", "sample", "objective", "fw", "camera")
    assert (by_position["GFP"].magnification, by_position["GFP"].band) == (5, (500, 550))
    assert by_position["RFP"].band == (575, None)
