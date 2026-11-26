"""Every operation of :class:`BasicInstrument`, run once through ``execute`` on simulated devices. A kind tests the
operations it declares itself the same way."""

import copy
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from vxl.instrument.basic import BasicInstrument

from .support import basic, profile, rig, simulated

_EXAMPLES: dict[str, Mapping[str, Any] | Callable[[BasicInstrument], Mapping[str, Any]]] = {
    "add_task": {"task": {"id": "a", "profiles": ["gfp"]}},
    "update_task": {"task_id": "a", "profiles": ["gfp", "rfp"]},
    "update_task_metadata": {"task_id": "a", "fields": {"notes": "left hemisphere"}},
    "reorder_tasks": {"task_ids": ["b", "a"]},
    "remove_tasks": {"task_ids": ["b"]},
    "rename_task": {"task_id": "a", "new_id": "c"},
    "update_profile": {"profile_id": "gfp", "label": "GFP"},
    "select_profile": {"profile_id": "gfp"},
    "apply_profile": {},
    "set_generator_timeline": lambda i: {
        "generator": "ao_main",
        "timeline": i.view.value.state.profiles["gfp"].timelines["ao_main"].model_dump(mode="json"),
    },
    "set_tuning_knob": {"generator": "ao_main", "wire": "galvo", "field": "amplitude", "value": 0.4},
    "set_power_mode": {"mode": "full"},
    "set_power": {"device": "laser", "value": 50.0},
    "set_dim_power": {"device": "laser", "value": 5.0},
    "stage_position": {},
    "set_position_rule": {"device_id": "fw", "rule": "GFP"},
    "set_metadata_class": {"cls": "vxl.metadata.ExperimentMetadata"},
    "save_as_default_state": {"paths": [["positions"]]},
    "restore_default_state": {"paths": [["positions"]]},
    "move_stage": {"x": 10.0, "wait": True},
    "lights_off": {},
    "lasers_off": {},
    "save_to_profile": {"device_id": "camera", "properties": ["exposure_time_ms", "binning"]},
    "restore_from_profile": {"device_id": "camera", "properties": ["exposure_time_ms"]},
    "remove_from_profile": {"device_id": "camera", "properties": ["binning"]},
    "undo": {},
    "redo": {},
    "stop": {},
}
"""1 valid call of each operation, in the order they run; a function builds arguments that need the instrument."""


@pytest.fixture
async def opened(tmp_path: Path) -> AsyncIterator[BasicInstrument]:
    """An open instrument on simulated devices, with a 2nd profile ``rfp``. Its profiles leave the filter wheel to the
    instrument, so a position rule can set it."""
    data = simulated(rig())
    del profile(data)["positions"]
    data["default"]["profiles"]["rfp"] = copy.deepcopy(profile(data))
    instrument = basic(data, tmp_path)
    await instrument.open()
    yield instrument
    await instrument.close()


def test_every_operation_has_an_example() -> None:
    assert set(BasicInstrument.operations) == set(_EXAMPLES)


async def test_every_operation_runs_and_each_state_change_is_1_undo_step(opened: BasicInstrument) -> None:
    for name, example in _EXAMPLES.items():
        if name == "reorder_tasks":
            await opened.execute("add_task", {"task": {"id": "b", "profiles": ["gfp"]}})
        args = example(opened) if callable(example) else example
        before = opened.view.value.state
        await opened.execute(name, args)
        if opened.operations[name].intent in ("create", "update", "delete") or name in (
            "reorder_tasks",
            "remove_tasks",
        ):
            assert opened.view.value.state != before, name
            await opened.execute("undo", {})
            assert opened.view.value.state == before, f"{name} is more than 1 undo step"
            await opened.execute("redo", {})
