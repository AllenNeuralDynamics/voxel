from typing import Annotated, Literal

import pytest
from pydantic import Field, ValidationError
from vxlib.schema import FrozenModel, check_identifier, duplicate_keys, error_message, repeated


def test_duplicate_keys_reports_each_shared_key_with_its_scopes_in_order():
    scopes = {
        "local": {"camera": 1, "stage": 2},
        "node:a": {"camera": 3, "laser": 4},
        "node:b": {"laser": 5, "camera": 6},
    }

    assert duplicate_keys(scopes) == {"camera": ["local", "node:a", "node:b"], "laser": ["node:a", "node:b"]}
    assert duplicate_keys({"a": {"x": 1}, "b": {"y": 2}}) == {}


def test_check_identifier_allows_only_letters_digits_underscore_and_hyphen():
    assert check_identifier("gfp_488-a", "Profile id") == "gfp_488-a"
    for value in ["gfp 488", "gfp.488", "gfp/rfp", "..", "gfp_é", ""]:
        with pytest.raises(ValueError, match="may use only letters, digits, '_' and '-'"):
            check_identifier(value, "Profile id")


def test_repeated_lists_each_repeat_once_in_first_repeat_order() -> None:
    assert repeated(["a", "b", "a", "c", "b", "a"]) == ["a", "b"]
    assert repeated([1, 2, 3]) == []


class _Clock(FrozenModel):
    kind: Literal["clock"]


class _Software(FrozenModel):
    kind: Literal["software"]


class _Scan(FrozenModel):
    pace: Annotated[_Clock | _Software, Field(discriminator="kind")]


def _errors(data: object) -> list[str]:
    with pytest.raises(ValidationError) as caught:
        _Scan.model_validate(data)
    return [error_message(error) for error in caught.value.errors()]


def test_error_message_says_plainly_that_the_tag_is_missing() -> None:
    assert _errors({"pace": {}}) == ["write 'kind': it picks 1 of the choices here"]


def test_error_message_keeps_pydantic_messages_that_are_already_clear() -> None:
    [message] = _errors({"pace": {"kind": "timer"}})
    assert "'clock', 'software'" in message
