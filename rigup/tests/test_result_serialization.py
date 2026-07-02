"""Serialization of a `Result` extracted from a batch `Results`.

A member pulled out of a deserialized `Results` retains the batch's generic type parameter, which
trips Pydantic's serializer when a downstream consumer (e.g. FastAPI's response model) dumps it
against a plain `Result` schema. `TransportNode.run_command` rebuilds a standalone `Result` to avoid
this; these tests pin that contract.
"""

import warnings

import pytest
from pydantic import TypeAdapter
from rigup.device.schema import Result, Results

_BATCH_JSON = '{"results":{"0:update_roi":{"ok":true,"value":{"x":0,"y":0,"w":4000,"h":2048}}}}'


def test_raw_batch_member_warns_on_serialization() -> None:
    """The unmodified extracted member serializes with a Pydantic serializer warning."""
    extracted = Results.model_validate_json(_BATCH_JSON).results["0:update_roi"]
    with pytest.warns(UserWarning, match="serialized value may not be as expected"):
        TypeAdapter(Result).dump_json(extracted)


def test_rebuilt_member_serializes_cleanly() -> None:
    """Rebuilding a standalone Result (as run_command does) serializes without warnings."""
    extracted = Results.model_validate_json(_BATCH_JSON).results["0:update_roi"]
    rebuilt = Result.model_validate(extracted.model_dump())
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any serializer warning becomes an error
        payload = TypeAdapter(Result).dump_json(rebuilt)
    assert b'"w":4000' in payload  # value survives the rebuild intact
