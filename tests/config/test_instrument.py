from typing import Any

import pytest
from pydantic import ValidationError

from vxl.config.instrument import InstrumentConfig, InstrumentTemplate, new_instrument_id

from .support import CONTEXT, load


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
    template = InstrumentTemplate.model_validate(template_data, context=CONTEXT)

    first, second = template.instantiate("left"), template.instantiate("right")
    assert first.id != second.id
    assert (first.name, first.model) == ("left", "exaspim.v2")
    assert InstrumentConfig.model_validate(first.model_dump(mode="json"), context=CONTEXT) == first


def test_a_template_has_no_id(config_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InstrumentTemplate.model_validate(config_data, context=CONTEXT)
