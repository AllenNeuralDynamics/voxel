from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from vxl._utils.files import load_yaml
from vxl.core.errors import RejectedError
from vxl.core.instrument.config import new_instrument_id
from vxl.core.instrument.folder import InstrumentFolder
from vxl.core.instrument.store import ABSENT, InstrumentStore
from vxl.instruments.spim.config import SPIMConfig, SPIMState, StageFollowRule, Task

from .support import codes, load, template, two_arms


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


def test_a_template_makes_instruments_with_new_ids(config_data: dict[str, Any], tmp_path: Path) -> None:
    first, second = (InstrumentFolder.create(template(config_data), name, tmp_path) for name in ("left", "right"))
    assert first.ok
    assert second.ok
    assert first.config is not None
    assert second.config is not None
    assert first.config.id != second.config.id
    assert (first.config.name, first.config.model) == ("left", "exaspim.v2")


def test_a_template_has_no_id(config_data: dict[str, Any], tmp_path: Path) -> None:
    with_identity = template(config_data)
    with_identity["rig"] |= {"id": config_data["id"], "name": config_data["name"]}
    with pytest.raises(RejectedError, match="a template has no id and no name"):
        InstrumentFolder.create(with_identity, "left", tmp_path)


def test_a_default_has_no_plan_and_no_metadata(config_data: dict[str, Any], tmp_path: Path) -> None:
    assert SPIMState.default_fields() == {"metadata_cls", "writer", "task", "positions", "profiles"}

    config_data["default"]["metadata"] = {"notes": "left hemisphere"}
    assert InstrumentFolder.create(template(config_data), "left", tmp_path).problems.codes() == ["default.not_default"]


async def test_the_store_keeps_the_plan_and_the_metadata_out_of_the_defaults(
    config_data: dict[str, Any], tmp_path: Path
) -> None:
    folder = InstrumentFolder.create(template(config_data), "left", tmp_path)
    home = folder.home
    assert isinstance(folder.config, SPIMConfig)
    assert isinstance(folder.default, SPIMState)
    store = InstrumentStore(home, folder.config, folder.default, folder.default)
    assert store.value == store.default_state.value
    assert store.last_modified is None

    xy = {"kind": "bounding_box", "points": [{"x": 0, "y": 0}, {"x": 500, "y": 500}]}
    region = {"xy": xy, "z": {"start": 0, "end": 100}}
    task = Task.complete({"id": "brain", "region": region, "profiles": ["gfp"]}, store.value.task)
    await store.update(
        {("plan",): [task], ("metadata",): {"notes": "left hemisphere"}, ("profiles", "gfp", "spacing"): 2.0}
    )
    assert store.last_modified is not None

    await store.save_as_default_state()
    assert store.default_state.value.profiles["gfp"].spacing == 2.0
    assert set(load_yaml(home / "default.yaml")) <= SPIMState.default_fields()
    with pytest.raises(RejectedError, match="plan"):
        await store.save_as_default_state(["plan"])

    await store.update({("profiles", "gfp", "spacing"): 3.0})
    await store.update(store.default_values())
    assert (store.value.profiles["gfp"].spacing, len(store.value.plan)) == (2.0, 1)
    assert store.value.metadata == {"notes": "left hemisphere"}

    with pytest.raises(RejectedError, match="'x_axis' is not a device of 'optics'"):
        await store.update({("positions", "x_axis"): 10})
    assert store.value.positions == store.default_state.value.positions

    again = InstrumentFolder.read(home)
    assert again.ok
    assert again.default == store.default_state.value
    assert again.state == store.value


async def test_the_store_sets_and_removes_values_at_key_paths(config_data: dict[str, Any], tmp_path: Path) -> None:
    folder = InstrumentFolder.create(template(config_data), "left", tmp_path)
    assert isinstance(folder.config, SPIMConfig)
    assert isinstance(folder.default, SPIMState)
    store = InstrumentStore(folder.home, folder.config, folder.default, folder.default)
    gfp = store.value.profiles["gfp"].model_dump()

    added = await store.update({("profiles", "rfp"): gfp | {"positions": {"fw": "RFP"}}})
    assert set(store.value.profiles) == {"gfp", "rfp"}
    assert added.before == {("profiles", "rfp"): ABSENT}

    removed = await store.update({("profiles", "rfp"): ABSENT})
    assert set(store.value.profiles) == {"gfp"}
    assert removed.after == {("profiles", "rfp"): ABSENT}

    with pytest.raises(RejectedError) as caught:
        await store.update({("profiles", "rfp", "spacing"): 2.0})
    assert [(problem.code, problem.loc) for problem in caught.value.problems] == [
        ("state.missing", ("profiles", "rfp", "spacing"))
    ]


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
    example = load(config_data)
    assert codes(example) == ["profile.position.two_levels"]
    assert [problem.loc for problem in example.problems()] == [("default", "profiles", "gfp", "positions", "fw")]


def test_a_device_that_1_profile_sets_each_profile_sets(config_data: dict[str, Any]) -> None:
    hal, profiles = config_data, config_data["default"]["profiles"]
    hal["devices"]["focus"] = {"target": "builtins.object"}
    hal["optics"]["objective"]["to"] = "focus"
    hal["optics"]["focus"] = {"to": "fw"}
    profiles["rfp"] = {**profiles["gfp"], "positions": {"fw": "RFP"}}
    assert codes(load(config_data)) == []

    profiles["gfp"]["positions"]["focus"] = 120.5
    example = load(config_data)
    assert codes(example) == ["profile.position.not_in_all_profiles"]
    assert [problem.loc for problem in example.problems()] == [("default", "profiles", "rfp", "positions", "focus")]

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
