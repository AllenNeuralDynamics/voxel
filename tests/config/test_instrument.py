from typing import Any

import pytest
from pydantic import ValidationError

from vxl.config.instrument import InstrumentConfig, InstrumentTemplate, new_instrument_id
from vxl.config.light import StageThreshold

from .support import codes, load


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


def test_default_is_checked_once_hal_and_engine_are_valid(config_data: dict[str, Any]) -> None:
    config_data["engine"]["target"] = "vxl.engines.spim.Nothing"
    with pytest.raises(ValidationError, match="default is checked once hal and engine are valid"):
        load(config_data)


def _arm_switch(config_data: dict[str, Any]) -> None:
    config_data["hal"]["devices"]["arm_switch"] = {
        "target": "builtins.object",
        "init": {"slots": {"0": "left", "1": "right"}},
    }
    config_data["hal"]["parts"].update(left_lens={}, right_lens={})
    config_data["hal"]["light"].update(
        {
            "laser": {"to": "arm_switch"},
            "arm_switch": {
                "to": {"left": "left_lens", "right": "right_lens"},
                "set_by": {"kind": "stage", "axis": "x", "lower": "left", "upper": "right"},
            },
            "left_lens": {"to": "galvo"},
            "right_lens": {"to": "galvo"},
            "galvo": {"to": "sample"},
        }
    )


def test_each_stage_rule_has_its_light_state(config_data: dict[str, Any]) -> None:
    _arm_switch(config_data)
    assert codes(load(config_data)) == ["light.state.missing"]
    config_data["default"]["light"] = {"arm_switch": {"threshold": 12000, "margin": 50}, "fw": {"threshold": 0}}
    assert codes(load(config_data)) == ["light.state.unexpected"]


def test_a_stage_rule_switches_with_hysteresis() -> None:
    state = StageThreshold(threshold=100, margin=10)
    assert [state.side(position) for position in (95, 105)] == ["lower", "upper"]
    assert state.side(105, previous="lower") == "lower"
    assert state.side(111, previous="lower") == "upper"
    assert state.side(95, previous="upper") == "upper"
    assert state.side(89, previous="upper") == "lower"
