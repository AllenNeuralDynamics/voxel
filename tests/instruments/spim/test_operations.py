"""Every operation of the SPIM microscope, run once through ``execute`` on simulated devices."""

from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from vxl_records import SQLiteRecords

from vxl.instruments.basic import BasicInstrument
from vxl.instruments.spim.instrument import Microscope
from vxl.instruments.spim.task import Task
from vxl.station.instrument.folder import InstrumentFolder
from vxl.system import System

from .support import simulated, template

_REGION = {"outline": {"kind": "explicit_points", "points": [{"x": 0, "y": 0}]}, "bounds": [0, 1]}


def _task(microscope: Microscope, task_id: str) -> Mapping[str, Any]:
    task = Task.complete({"id": task_id, "region": _REGION, "profiles": ["gfp"]}, microscope.view.value.state.task)
    return {"task": task.model_dump(mode="json")}


_EXAMPLES: dict[str, Mapping[str, Any] | Callable[[Microscope], Mapping[str, Any]]] = {
    "add_task": lambda m: _task(m, "a"),
    "update_task": {"task_id": "a", "overlap": {"x": "20 %", "y": "10 %"}},
    "reorder_tasks": {"task_ids": ["b", "a"]},
    "remove_tasks": {"task_ids": ["b"]},
    "update_profile": {"profile_id": "gfp", "spacing": 2.5, "label": "GFP"},
    "update_writer_settings": {"shard_z_chunks": 4},
    "select_profile": {"profile_id": "gfp"},
    "apply_profile": {},
    "set_generator_timeline": lambda m: {
        "generator": "ao_main",
        "timeline": m.view.value.state.profiles["gfp"].timelines["ao_main"].model_dump(mode="json"),
    },
    "set_power_mode": {"mode": "full"},
    "set_power": {"device": "laser", "value": 50.0},
    "set_dim_power": {"device": "laser", "value": 5.0},
    "stage_position": {},
    "set_position_rule": {"device_id": "fw", "rule": "GFP"},
    "update_metadata": {"fields": {"notes": "left hemisphere"}},
    "set_metadata_class": {"cls": "vxl.metadata.ExperimentMetadata"},
    "save_as_default_state": {"fields": ["writer"]},
    "restore_default_state": {"fields": ["writer"]},
    "move_stage": {"x": 10.0, "wait": True},
    "set_preview_channels": {"channels": ["camera"]},
    "set_camera_region": {"camera": "camera", "region": None},
    "start_preview": {},
    "stop_preview": {},
    "lights_off": {},
    "lasers_off": {},
    "undo": {},
    "redo": {},
    "stop": {},
}
"""1 valid call of each operation, in the order they run; a function builds arguments that need the instrument."""


_EDITS = {"reorder_tasks", "remove_tasks", "set_position_rule", "update_metadata"}
"""Actions that edit the saved state, and so must be 1 undo step too."""


@pytest.fixture
async def opened(config_data: dict[str, Any], tmp_path: Path) -> AsyncIterator[Microscope]:
    """An open microscope on simulated devices. Its profile leaves the filter wheel to the instrument, so a position
    rule can set it."""
    del config_data["default"]["profiles"]["gfp"]["positions"]
    folder = InstrumentFolder.create(template(simulated(config_data)), "left", tmp_path)
    records = SQLiteRecords(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    microscope = Microscope(folder, records=records, system=system)
    await microscope.open()
    yield microscope
    await microscope.close()


def test_every_operation_of_every_shipped_kind_has_an_example() -> None:
    assert set(Microscope.operations) == set(_EXAMPLES)
    assert set(BasicInstrument.operations) <= set(_EXAMPLES)


async def test_every_operation_runs_and_each_state_change_is_1_undo_step(opened: Microscope) -> None:
    for name, example in _EXAMPLES.items():
        if name == "reorder_tasks":
            await opened.execute("add_task", _task(opened, "b"))
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
