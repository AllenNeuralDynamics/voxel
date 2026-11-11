from typing import Any

import pytest
from pydantic import ValidationError

from vxl.spim.config import InstrumentConfig, InstrumentTemplate, StageFollowRule, new_instrument_id

from .support import codes, load, two_arms


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


def test_a_template_makes_instruments_with_new_ids(config_data: dict[str, Any]) -> None:
    template_data = {key: value for key, value in config_data.items() if key not in {"id", "name"}}
    template = InstrumentTemplate.model_validate(template_data)

    first, second = template.instantiate("left"), template.instantiate("right")
    assert first.id != second.id
    assert (first.name, first.model) == ("left", "exaspim.v2")
    assert InstrumentConfig.model_validate(first.model_dump(mode="json")) == first


def test_a_template_has_no_id(config_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InstrumentTemplate.model_validate(config_data)


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
        ({"arm_switch": "up"}, ["positions.invalid"]),
        ({"arm_switch": {**_FOLLOW_X, "order": ["left", "up"]}}, ["positions.invalid"]),
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
    config = load(config_data)
    assert codes(config) == ["profile.position.two_levels"]
    assert [violation.loc for violation in config.violations()] == [("default", "profiles", "gfp", "positions", "fw")]


def test_a_device_that_1_profile_sets_each_profile_sets(config_data: dict[str, Any]) -> None:
    hal, profiles = config_data["hal"], config_data["default"]["profiles"]
    hal["devices"]["focus"] = {"target": "builtins.object"}
    hal["optics"]["objective"]["to"] = "focus"
    hal["optics"]["focus"] = {"to": "fw"}
    profiles["rfp"] = {**profiles["gfp"], "positions": {"fw": "RFP"}}
    assert codes(load(config_data)) == []

    profiles["gfp"]["positions"]["focus"] = 120.5
    config = load(config_data)
    assert codes(config) == ["profile.position.not_in_all_profiles"]
    assert [violation.loc for violation in config.violations()] == [
        ("default", "profiles", "rfp", "positions", "focus")
    ]

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
