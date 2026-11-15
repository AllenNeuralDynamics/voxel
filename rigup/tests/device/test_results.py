import warnings
from typing import NamedTuple

import pytest
from pydantic import TypeAdapter
from rigup.device import Result
from rigup.device.results import PropModel, PropResults, Results

BATCH_JSON = '{"results":{"0:update_roi":{"ok":true,"value":{"x":0,"y":0,"w":4000,"h":2048}}}}'


class Range(NamedTuple):
    low: float
    high: float


def test_a_member_taken_from_a_batch_warns_when_dumped_as_a_plain_result() -> None:
    extracted = Results.model_validate_json(BATCH_JSON).results["0:update_roi"]

    with pytest.warns(UserWarning, match="serialized value may not be as expected"):
        TypeAdapter(Result).dump_json(extracted)


def test_a_rebuilt_batch_member_dumps_cleanly() -> None:
    extracted = Results.model_validate_json(BATCH_JSON).results["0:update_roi"]
    rebuilt = Result.model_validate(extracted.model_dump())

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        payload = TypeAdapter(Result).dump_json(rebuilt)

    assert b'"w":4000' in payload


@pytest.mark.parametrize(
    ("value", "crossed"), [(Range(-5.0, 5.0), [-5.0, 5.0]), ((1, 2), [1, 2])], ids=["named-tuple", "tuple"]
)
def test_a_tuple_value_crosses_as_a_list(value: tuple[float, ...], crossed: list[float]) -> None:
    assert PropModel.from_value(value).value == crossed


def test_prop_results_with_limits_round_trip_through_json() -> None:
    results = PropResults(
        results={
            "level": Result.ok(PropModel(kind="float", value=25.5, options=[0.0, 25.5, 100.0])),
            "binning": Result.err("binning cannot be 3"),
        }
    )

    restored = PropResults.model_validate_json(results.model_dump_json())

    assert restored == results


def test_a_result_gives_its_error_only_when_it_failed() -> None:
    assert Result.err("no power").error == "no power"
    assert Result.ok(1.0).error is None


def test_results_list_the_errors_of_failed_entries() -> None:
    found = Results(results={"power": Result.ok(1.0), "mode": Result.err("bad mode")})

    assert found.errors == {"mode": "bad mode"}
