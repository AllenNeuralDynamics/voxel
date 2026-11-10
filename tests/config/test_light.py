from typing import Any

import pytest
from pydantic import ValidationError

from vxl.config.light import LightGraph

from .support import codes, load


def _light(data: dict[str, Any]) -> dict[str, Any]:
    return data["hal"]["light"]


def _two_arms(data: dict[str, Any], rule: str | dict[str, Any]) -> dict[str, Any]:
    """A switch that sends the laser to 1 of 2 arms, set by ``rule``."""
    data["hal"]["devices"]["arm_switch"] = {"target": "builtins.object", "init": {"slots": {"0": "left", "1": "right"}}}
    data["hal"]["parts"].update(left_lens={}, right_lens={})
    _light(data).update(
        {
            "laser": {"to": "arm_switch"},
            "arm_switch": {"to": {"left": "left_lens", "right": "right_lens"}, "set_by": rule},
            "left_lens": {"to": "galvo"},
            "right_lens": {"to": "galvo"},
            "galvo": {"to": "sample"},
        }
    )
    return data


def test_a_typo_in_where_the_light_goes(config_data: dict[str, Any]) -> None:
    _light(config_data)["sample"]["to"] = "fw_emision"
    assert "hal.light.target_missing" in codes(load(config_data))


def test_a_node_is_a_device_or_a_part(config_data: dict[str, Any]) -> None:
    del config_data["hal"]["parts"]["galvo"]
    found = codes(load(config_data))
    assert "hal.light.node_unknown" in found
    assert "hal.wiring.receiver_missing" in found


def test_only_a_part_has_a_kind(config_data: dict[str, Any]) -> None:
    _light(config_data)["fw"] = {"kind": "combiner", "to": "camera"}
    assert "hal.light.kind_on_device" in codes(load(config_data))


def test_a_kind_is_combiner_or_splitter(config_data: dict[str, Any]) -> None:
    _light(config_data)["galvo"] = {"kind": "lens", "to": "sample"}
    with pytest.raises(ValidationError, match="a node's kind is combiner or splitter"):
        load(config_data)


def test_only_a_splitter_sends_light_to_several_parts_at_once(config_data: dict[str, Any]) -> None:
    _light(config_data)["laser"] = {"to": ["galvo", "sample"]}
    with pytest.raises(ValidationError):
        load(config_data)
    _light(config_data)["laser"] = {"kind": "splitter", "to": ["galvo"]}
    with pytest.raises(ValidationError, match="at least 2"):
        load(config_data)


def test_a_device_without_slots_cannot_send_light_by_position(config_data: dict[str, Any]) -> None:
    _light(config_data)["laser"] = {"to": {"on": "galvo"}, "set_by": "profile"}
    found = codes(load(config_data))
    assert "hal.light.positions_missing" in found


def test_positions_in_to_are_the_devices_slots(config_data: dict[str, Any]) -> None:
    _two_arms(config_data, {"kind": "stage", "axis": "x", "lower": "left", "upper": "right"})
    _light(config_data)["arm_switch"]["to"]["up"] = "left_lens"
    config_data["default"]["light"] = {"arm_switch": {"threshold": 0}}
    assert "hal.light.position_unknown" in codes(load(config_data))


def test_a_switch_needs_a_rule(config_data: dict[str, Any]) -> None:
    _two_arms(config_data, "profile")
    del _light(config_data)["arm_switch"]["set_by"]
    with pytest.raises(ValidationError, match=r"arm_switch\.switch\.set_by\s+Field required"):
        load(config_data)


def test_only_a_device_is_set_by_a_rule(config_data: dict[str, Any]) -> None:
    _light(config_data)["galvo"]["set_by"] = "profile"
    assert "hal.light.set_by_not_device" in codes(load(config_data))


@pytest.mark.parametrize(
    ("rule", "code"),
    [
        ({"kind": "stage", "axis": "x", "lower": "left", "upper": "up"}, "hal.light.position_unknown"),
        ({"kind": "stage", "axis": "z", "lower": "left", "upper": "right"}, "hal.light.stage_axis_moving"),
    ],
)
def test_rule_positions_and_axes(config_data: dict[str, Any], rule: dict[str, Any], code: str) -> None:
    _two_arms(config_data, rule)
    config_data["default"]["light"] = {"arm_switch": {"threshold": 0}}
    assert code in codes(load(config_data))


def test_a_rule_that_picks_a_label_needs_slots(config_data: dict[str, Any]) -> None:
    _light(config_data)["laser"]["set_by"] = {"kind": "stage", "axis": "x", "lower": "a", "upper": "b"}
    assert "hal.light.set_by_needs_slots" in codes(load(config_data))


def test_a_cameras_path_gives_a_magnification(config_data: dict[str, Any]) -> None:
    del _light(config_data)["objective"]["magnification"]
    assert "hal.light.magnification_missing" in codes(load(config_data))


def test_width_and_height_are_at_right_angles(config_data: dict[str, Any]) -> None:
    _light(config_data)["camera"]["height"] = {"x": 1, "y": 0.1}
    with pytest.raises(ValidationError, match="at 90°"):
        load(config_data)


def test_the_graph_has_a_sample(config_data: dict[str, Any]) -> None:
    del _light(config_data)["sample"]
    found = codes(load(config_data))
    assert "hal.light.sample_missing" in found
    assert "hal.light.target_missing" in found


def test_magnification_is_the_product_after_the_sample() -> None:
    light = LightGraph.model_validate(
        {
            "laser": {"to": "sample"},
            "sample": {"to": "objective"},
            "objective": {"magnification": 20, "to": "splitter"},
            "splitter": {"kind": "splitter", "to": ["tube_a", "camera_b"]},
            "tube_a": {"magnification": 0.5, "to": "camera_a"},
            "camera_a": {"width": {"y": 1}},
            "camera_b": {"width": {"y": 1}},
        }
    )
    assert list(light.sources()) == ["laser"]
    assert list(light.detectors()) == ["camera_a", "camera_b"]
    (to_a,) = light.paths("laser", "camera_a")
    (to_b,) = light.paths("laser", "camera_b")
    assert (to_a.magnification, to_b.magnification) == (10, 20)
    assert to_a.nodes == ("laser", "sample", "objective", "splitter", "tube_a", "camera_a")


def test_a_switch_gives_1_path_for_each_position(config_data: dict[str, Any]) -> None:
    _two_arms(config_data, {"kind": "stage", "axis": "x", "lower": "left", "upper": "right"})
    config_data["default"]["light"] = {"arm_switch": {"threshold": 0}}
    paths = load(config_data).hal.light.paths("laser", "camera")
    assert sorted(path.positions["arm_switch"] for path in paths) == ["left", "right"]
