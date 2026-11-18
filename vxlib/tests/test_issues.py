from datetime import UTC, datetime
from typing import Self

import pytest
from pydantic import BaseModel, ValidationError, model_validator
from vxlib.issues import Alert, Issue, Problem, Problems


class _Rig(BaseModel, frozen=True):
    nodes: dict[str, list[str]]

    @model_validator(mode="after")
    def _check(self) -> Self:
        found = Problems()
        seen: dict[str, str] = {}
        for node, uids in self.nodes.items():
            for uid in uids:
                if uid in seen:
                    msg = f"'{uid}' is also on node '{seen[uid]}'"
                    found.add("duplicate_uid", msg, "nodes", node, uid, detail=f"first on {seen[uid]}")
                seen[uid] = node
        found.raise_if_any(type(self).__name__)
        return self


class _Instrument(BaseModel, frozen=True):
    rig: _Rig


def test_a_validator_raises_every_problem_at_once_and_each_comes_back_with_its_place_and_detail():
    with pytest.raises(ValidationError) as caught:
        _Instrument.model_validate({"rig": {"nodes": {"a": ["x", "y"], "b": ["x", "y"]}}})

    found = Problems.from_validation(caught.value, "file")

    assert found == [
        Problem(
            code="file.duplicate_uid",
            msg="'x' is also on node 'a'",
            loc=("file", "rig", "nodes", "b", "x"),
            detail="first on a",
        ),
        Problem(
            code="file.duplicate_uid",
            msg="'y' is also on node 'a'",
            loc=("file", "rig", "nodes", "b", "y"),
            detail="first on a",
        ),
    ]


def test_no_problems_raise_nothing():
    Problems().raise_if_any("Nothing")
    assert _Rig(nodes={"a": ["x"], "b": ["y"]}).nodes == {"a": ["x"], "b": ["y"]}


def test_a_plain_pydantic_error_becomes_a_problem_with_no_detail():
    with pytest.raises(ValidationError) as caught:
        _Rig.model_validate({"nodes": 1})

    assert Problems.from_validation(caught.value, "rig") == [
        Problem(code="rig.dict_type", msg="Input should be a valid dictionary", loc=("rig", "nodes"))
    ]


def test_under_puts_keys_in_front_of_each_place():
    found = Problems([Problem(code="a", msg="first", loc=("x",)), Problem(code="b", msg="second")])

    assert [problem.loc for problem in found.under("state", 0)] == [("state", 0, "x"), ("state", 0)]
    assert found.codes() == ["a", "b"]
    assert str(found) == "first; second"


def test_assignments_names_each_missing_and_each_unexpected_key():
    found = Problems.assignments(expected={"x", "y"}, assigned={"y", "z"}, code="stage", label="axis")

    assert [(problem.code, problem.loc) for problem in found] == [
        ("stage.missing", ("x",)),
        ("stage.unexpected", ("z",)),
    ]


def test_a_problem_is_an_issue_that_is_always_an_error() -> None:
    problem = Problem(code="rig.x", msg="wrong", loc=("devices", "camera"))
    assert isinstance(problem, Issue)
    assert problem.level == "error"
    with pytest.raises(ValidationError):
        Problem.model_validate({"code": "rig.x", "msg": "wrong", "level": "warning"})


def test_an_alert_is_an_issue_that_started_at_a_time() -> None:
    since = datetime(2026, 11, 17, 10, 42, tzinfo=UTC)
    alert = Alert(
        code="camera.no_frames", level="error", msg="Camera sends no frames.", loc=("devices", "camera"), since=since
    )
    assert isinstance(alert, Issue)
    assert alert.since == since
