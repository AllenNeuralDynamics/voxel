from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel, Field
from rigup.activity import ActivityBusyError, ActivityInfo
from rigup.device import DeviceInterface, PropModel
from vxlib.issues import Problems

from vxl.instrument.base import Instrument
from vxl.instrument.basic import BasicInstrument
from vxl.instrument.config import InstrumentConfig
from vxl.instrument.folder import FolderFile, InstrumentFolder
from vxl.instrument.hal import DeviceView
from vxl.instrument.state import InstrumentState, ProfileFields, Task
from vxl.instrument.store import Merge
from vxl.metadata import ExperimentMetadata, key, required
from vxl.records import Records
from vxl.station.errors import NotFoundError, RejectedError, StartupError
from vxl.system import System

from .support import bench

if TYPE_CHECKING:
    from collections.abc import Mapping


_AXIS = "vxl.devices.axes.continuous.simulated.SimulatedLinearAxis"

_RIG: dict[str, Any] = {
    "devices": {
        "daq_hub": {
            "target": "vxl.devices.signals.cards.simulated.SimulatedDaqmx",
            "init": {"device_name": "MockDev1"},
        },
        "daq": {
            "target": "vxl.devices.signals.generator.simulated.SimulatedGenerator",
            "init": {"hub": "daq_hub"},
        },
        "camera": {
            "target": "vxl.devices.camera.simulated.SimulatedCamera",
            "init": {"frame_source": {"sensor_size_px": {"x": 64, "y": 64}, "pixel_size_um": {"x": 3.76, "y": 3.76}}},
        },
        "laser_488": {
            "target": "vxl.devices.light.simulated.SimulatedLaser",
            "init": {"wavelength": 488},
        },
        "x_axis": {"target": _AXIS, "init": {"lower": 0, "upper": 1000, "speed": 100_000}},
        "y_axis": {"target": _AXIS, "init": {"lower": 0, "upper": 1000, "speed": 100_000}},
        "z_axis": {"target": _AXIS, "init": {"lower": 0, "upper": 1000, "speed": 100_000}},
    },
    "stage": {"x": {"device": "x_axis"}, "y": {"device": "y_axis"}, "z": {"device": "z_axis"}},
    "optics": {
        "laser_488": {"to": "specimen"},
        "specimen": {"to": "camera"},
        "camera": {"width": {"y": 1}, "height": {"x": -1}},
    },
}

_DEFAULT: dict[str, Any] = {"profiles": {"main": {"channels": {"main": {"camera": "laser_488"}}}}}


class _State(InstrumentState, frozen=True):
    def problems(self, config: InstrumentConfig) -> Problems:
        """No rules of its own: only the rig's."""
        return config.problems()


class _Bench(Instrument[InstrumentConfig, _State]):
    """The smallest kind of instrument: the base config and a state with no rules. Its 1 command opens an edit and
    calls another command inside it, then raises ``fail`` when given."""

    async def label_main(self, label: str | None, desc: str, *, fail: Exception | None = None) -> None:
        async with self._state_edit("Label main") as edit:
            await edit.record({("profiles", "main", "label"): label})
            await self._update_profile("main", {"desc": desc}, ProfileFields)
            if fail is not None:
                raise fail


def _folder(
    tmp_path: Path, rig: dict[str, Any], kind: type[_Bench] | None = None
) -> InstrumentFolder[InstrumentConfig, _State]:
    """A folder as :meth:`InstrumentFolder.read` gives it, with no files on disk."""
    return InstrumentFolder(
        tmp_path,
        kind,
        FolderFile(data=rig, model=bench(rig)),
        FolderFile(data=_DEFAULT, model=_State.model_validate(_DEFAULT)),
        FolderFile(data=None),
        Problems(),
    )


def _instrument(tmp_path: Path, rig: dict[str, Any]) -> _Bench:
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    return _Bench(_folder(tmp_path, rig, _Bench), records=records, system=system)


@pytest.fixture
async def instrument(tmp_path: Path) -> AsyncIterator[_Bench]:
    instrument = _instrument(tmp_path, _RIG)
    await instrument.open()
    try:
        yield instrument
    finally:
        await instrument.close()


async def test_open_asks_every_device_what_it_is(instrument: _Bench) -> None:
    views = instrument.view.value.devices
    kinds = {device_id: view.interface.kind for device_id, view in views.items()}

    assert set(kinds) == set(_RIG["devices"])
    assert (kinds["camera"], kinds["laser_488"], kinds["x_axis"]) == ("area_camera", "laser", "linear_axis")
    assert views["laser_488"].props


async def test_a_property_set_is_written_and_shown(instrument: _Bench) -> None:
    sent: list[Mapping[str, DeviceView]] = []
    instrument.view.subscribe(lambda view: sent.append(view.devices))

    results = await instrument.set_device_properties("camera", {"exposure_time_ms": 12.5})

    assert results.ok["exposure_time_ms"].value == 12.5
    assert sent
    assert instrument.view.value.devices["camera"].props["exposure_time_ms"].value == 12.5


def _alerts(instrument: _Bench) -> list[tuple[str, tuple[str | int, ...]]]:
    return [(alert.code, alert.loc) for alert in instrument.view.value.alerts]


async def test_a_device_that_differs_from_the_profile_is_an_alert_until_either_takes_the_others_value(
    instrument: _Bench,
) -> None:
    exposure = ("device.inconsistent_with_profile", ("devices", "camera", "props", "exposure_time_ms"))
    await instrument.set_device_properties("camera", {"exposure_time_ms": 20.0})
    assert _alerts(instrument) == []  # the profile sets no exposure yet

    await instrument.save_to_profile("camera", ["exposure_time_ms"])
    assert instrument.view.value.state.profiles["main"].props == {"camera": {"exposure_time_ms": 20.0}}
    assert instrument.view.value.history.undo_label == "Save to profile"

    await instrument.set_device_properties("camera", {"exposure_time_ms": 35.0})
    assert _alerts(instrument) == [exposure]
    since = instrument.view.value.alerts[0].since
    await instrument.set_device_properties("camera", {"exposure_time_ms": 36.0})
    assert instrument.view.value.alerts[0].since == since
    assert "is 36.0, the profile has 20.0" in instrument.view.value.alerts[0].msg

    await instrument.restore_from_profile("camera", ["exposure_time_ms"])
    assert instrument.view.value.devices["camera"].props["exposure_time_ms"].value == 20.0
    assert _alerts(instrument) == []

    await instrument.set_device_properties("camera", {"exposure_time_ms": 36.0})
    await instrument.save_to_profile("camera", ["exposure_time_ms"])
    assert _alerts(instrument) == []


async def test_a_number_differs_from_the_profile_by_more_than_half_a_step(instrument: _Bench) -> None:
    exposure = ("device.inconsistent_with_profile", ("devices", "camera", "props", "exposure_time_ms"))
    await instrument.set_device_properties("camera", {"exposure_time_ms": 20})
    assert instrument.view.value.devices["camera"].props["exposure_time_ms"].step == 0.001

    # A profile can hold a finer value than the camera reports: within half a step, the camera is at that value.
    await instrument._store.update({("profiles", "main", "props", "camera"): Merge({"exposure_time_ms": 20.0004})})
    assert _alerts(instrument) == []

    await instrument._store.update({("profiles", "main", "props", "camera"): Merge({"exposure_time_ms": 20.0006})})
    assert _alerts(instrument) == [exposure]


def test_the_position_of_an_axis_with_named_slots_is_the_label_of_its_slot() -> None:
    def wheel(position: str | None, slot: int | None) -> DeviceView:
        state = {"position": position, "slot": slot, "target": 1, "is_moving": False}
        return DeviceView(
            interface=DeviceInterface(id="fw", kind="discrete_axis"), props={"state": PropModel[Any](value=state)}
        )

    assert Instrument._last_value(wheel("RFP", 1), "position") == ("RFP", None)
    assert Instrument._last_value(wheel(None, 1), "position") == (1, None)  # no label: differs from every label
    assert Instrument._last_value(wheel(None, None), "position") is None  # between slots: nothing to compare


async def test_the_view_names_the_operation_that_runs_and_the_alerts_stay_as_they_were_inside_it(
    instrument: _Bench,
) -> None:
    await instrument.set_device_properties("camera", {"exposure_time_ms": 20.0})
    await instrument.save_to_profile("camera", ["exposure_time_ms"])
    await instrument.set_device_properties("camera", {"exposure_time_ms": 35.0})
    seen: list[tuple[str | None, int]] = []
    instrument.view.subscribe(lambda view: seen.append((view.operation, len(view.alerts))))

    await instrument.restore_from_profile("camera", ["exposure_time_ms"])

    assert seen[0] == ("restoring camera from profile", 1)
    assert seen[-1] == (None, 0)
    assert {alerts for operation, alerts in seen if operation is not None} == {1}  # as they were, until it ends


async def test_saving_or_restoring_a_value_that_is_not_there_is_not_found(instrument: _Bench) -> None:
    with pytest.raises(NotFoundError, match="has not reported"):
        await instrument.save_to_profile("camera", ["no_such_property"])
    with pytest.raises(NotFoundError, match="The active profile has no"):
        await instrument.restore_from_profile("camera", ["exposure_time_ms"])
    with pytest.raises(NotFoundError, match="Device 'nope' not found"):
        await instrument.save_to_profile("nope", [])
    with pytest.raises(NotFoundError, match="Device 'nope' not found"):
        await instrument.restore_from_profile("nope", [])


async def test_a_profile_takes_only_what_a_device_can_set_and_never_a_stage_position(instrument: _Bench) -> None:
    with pytest.raises(RejectedError, match="cannot set"):
        await instrument.save_to_profile("camera", ["frame_size_mb"])
    with pytest.raises(RejectedError, match="is a stage axis"):
        await instrument.save_to_profile("x_axis", ["position"])

    assert instrument.view.value.state.profiles["main"].props == {}
    await instrument.apply_profile()  # the profile still applies


async def test_a_value_removed_from_the_profile_is_undone_as_1_step(instrument: _Bench) -> None:
    await instrument.set_device_properties("camera", {"exposure_time_ms": 20.0})
    await instrument.save_to_profile("camera", ["exposure_time_ms"])

    await instrument.remove_from_profile("camera", ["exposure_time_ms"])
    assert instrument.view.value.state.profiles["main"].props == {}
    assert instrument.view.value.history.undo_label == "Remove from profile"
    with pytest.raises(NotFoundError, match="The active profile has no"):
        await instrument.remove_from_profile("camera", ["exposure_time_ms"])

    await instrument.undo()
    assert instrument.view.value.state.profiles["main"].props == {"camera": {"exposure_time_ms": 20.0}}


async def test_a_save_to_the_profile_is_undone_as_1_step(instrument: _Bench) -> None:
    await instrument.set_device_properties("camera", {"exposure_time_ms": 20.0})
    await instrument.save_to_profile("camera", ["exposure_time_ms"])
    await instrument.set_device_properties("camera", {"exposure_time_ms": 35.0})

    await instrument.undo()

    assert instrument.view.value.state.profiles["main"].props == {}
    assert _alerts(instrument) == []  # the profile sets no exposure again


async def test_a_metadata_edit_replaces_a_map_of_free_keys_whole(instrument: _Bench) -> None:
    await _with_task(instrument)
    await instrument.set_metadata_class(_SubjectMetadata)
    await instrument._update_task_metadata("brain", {"tags": {"a": "1", "b": "2"}})

    await instrument._update_task_metadata("brain", {"tags": {"a": "9"}})

    assert _metadata(instrument)["tags"] == {"a": "9"}


async def test_the_views_are_empty_after_close(instrument: _Bench) -> None:
    await instrument.close()

    assert instrument.view.value.devices == {}


async def test_a_device_command_runs(instrument: _Bench) -> None:
    result = await instrument.execute_device_command("laser_488", "off")

    assert result.is_ok


async def test_move_stage_moves_only_the_given_axes(instrument: _Bench) -> None:
    await instrument.move_stage(x=100, z=250, wait=True)

    stage = instrument._hal.stage
    positions = {axis: await stage[axis].position.get() for axis in ("x", "y", "z")}
    assert positions == {"x": 100, "y": 0, "z": 250}


async def test_a_stage_move_outside_the_limits_is_refused_and_no_axis_moves(instrument: _Bench) -> None:
    stage = instrument._hal.stage
    limit = (await stage["z"].get_limits()).high

    for z in (limit + 1, float("inf"), float("nan")):
        with pytest.raises(RejectedError, match=r"The stage cannot go to .* on z"):
            await instrument.move_stage(x=100, z=z, wait=True)

    assert await stage["x"].position.get() == 0


async def test_a_metadata_form_that_is_no_metadata_class_is_refused(instrument: _Bench) -> None:
    for path in ("no.such.Thing", "os.getcwd", "nodots"):
        with pytest.raises(RejectedError, match="not the path of a metadata class"):
            await instrument.execute("set_metadata_class", {"cls": path})


async def _nothing() -> None:
    pass


async def test_a_device_command_runs_while_an_activity_holds_the_device(instrument: _Bench) -> None:
    scheduler = instrument._scheduler
    async with scheduler.run("start a calibration", requires=()):
        await scheduler.start(ActivityInfo(kind="calibration"), {"laser_488"}, stop=_nothing)

    result = await instrument.execute_device_command("laser_488", "off")

    assert result.is_ok
    assert [activity.kind for activity in instrument.view.value.activities] == ["calibration"]


async def test_a_device_action_is_refused_while_an_activity_that_cannot_restart_holds_the_device(
    instrument: _Bench,
) -> None:
    scheduler = instrument._scheduler
    async with scheduler.run("start a calibration", requires=()):
        await scheduler.start(ActivityInfo(kind="calibration"), {"laser_488"}, stop=_nothing)

    with pytest.raises(ActivityBusyError, match="Running laser_488 on is not possible while calibration is running"):
        await instrument.execute_device_command("laser_488", "on")


async def test_a_device_of_the_wrong_kind_stops_the_start(tmp_path: Path) -> None:
    rig = {**_RIG, "stage": {"x": {"device": "daq"}, "y": {"device": "y_axis"}, "z": {"device": "z_axis"}}}
    instrument = _instrument(tmp_path, rig)

    with pytest.raises(StartupError) as caught:
        await instrument.open()

    assert caught.value.problems.codes() == ["rig.device.not_linear_axis"]


async def test_a_device_with_2_roles_is_checked_for_each(tmp_path: Path) -> None:
    rig = {**_RIG, "stage": {"x": {"device": "camera"}, "y": {"device": "y_axis"}, "z": {"device": "z_axis"}}}
    instrument = _instrument(tmp_path, rig)

    with pytest.raises(StartupError) as caught:
        await instrument.open()

    assert caught.value.problems.codes() == ["rig.device.not_linear_axis"]


def test_a_kind_names_its_config_and_state_classes_in_its_class_line() -> None:
    assert (_Bench.config_cls, _Bench.state_cls) == (InstrumentConfig, _State)

    class _Child(_Bench):
        pass

    assert (_Child.config_cls, _Child.state_cls) == (InstrumentConfig, _State)


def _create(tmp_path: Path, target: str) -> InstrumentFolder:
    return InstrumentFolder.create({"rig": {**_RIG, "target": target}, "default": _DEFAULT}, "bench", tmp_path)


def test_read_finds_the_kind_and_reads_the_files(tmp_path: Path) -> None:
    folder = _create(tmp_path, f"{__name__}._Bench")

    assert folder.ok, folder.problems
    assert folder.kind is _Bench
    assert isinstance(folder.default.model, _State)
    assert InstrumentFolder.read(folder.home) == folder


def test_read_gives_a_problem_for_a_target_it_cannot_import(tmp_path: Path) -> None:
    assert _create(tmp_path, "nowhere.Kind").problems.codes() == ["rig.target"]
    assert InstrumentFolder.read(tmp_path / "empty.voxel").problems.codes() == ["rig.missing"]


def test_the_folder_builds_the_instrument_of_its_kind(tmp_path: Path) -> None:
    folder = _create(tmp_path, f"{__name__}._Bench")
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)

    assert type(folder.instrument(records=records, system=system)) is _Bench

    class _Other(Instrument[InstrumentConfig, _State]):
        pass

    with pytest.raises(TypeError, match="is run by _Bench, not by _Other"):
        _Other(folder, records=records, system=system)


class _LabMetadata(ExperimentMetadata):
    operator: str = ""


class _Chamber(BaseModel):
    medium: str = required(default="other")
    refractive_index: float = 1.33


class _SubjectMetadata(ExperimentMetadata):
    subject_id: str = key(default="")
    experimenters: list[str] = required(default_factory=list)
    chamber: _Chamber = Field(default_factory=_Chamber)
    spare: _Chamber | None = None
    tags: dict[str, str] = Field(default_factory=dict)


async def _with_task(instrument: _Bench) -> None:
    await instrument._add_task(Task(id="brain", profiles=["main"]))


def _metadata(instrument: _Bench) -> dict[str, Any]:
    return instrument.view.value.state.plan[0].metadata


async def test_a_task_metadata_edit_can_be_undone_and_redone(instrument: _Bench) -> None:
    await _with_task(instrument)
    await instrument._update_task_metadata("brain", {"notes": "left hemisphere"})
    assert _metadata(instrument)["notes"] == "left hemisphere"
    assert instrument.view.value.history.undo_label == "Update task metadata"

    await instrument.undo()
    assert _metadata(instrument).get("notes", "") == ""
    await instrument.redo()
    assert _metadata(instrument)["notes"] == "left hemisphere"


async def test_metadata_that_does_not_fit_its_form_is_rejected_at_its_field(instrument: _Bench) -> None:
    await _with_task(instrument)
    with pytest.raises(RejectedError) as caught:
        await instrument._update_task_metadata("brain", {"weight": 12})

    assert [problem.loc for problem in caught.value.problems] == [("plan", 0, "metadata", "weight")]
    assert instrument.view.value.history.undo_label == "Add task"


async def test_an_edit_of_1_field_of_a_metadata_group_keeps_the_others(instrument: _Bench) -> None:
    await _with_task(instrument)
    await instrument.set_metadata_class(_SubjectMetadata)
    await instrument._update_task_metadata("brain", {"chamber": {"medium": "oil", "refractive_index": 1.52}})

    await instrument._update_task_metadata("brain", {"chamber": {"medium": "water"}})

    assert _metadata(instrument)["chamber"] == {"medium": "water", "refractive_index": 1.52}


async def test_the_view_gives_the_schema_of_the_metadata_form_with_the_plan_that_fits_it(instrument: _Bench) -> None:
    await _with_task(instrument)
    assert "subject_id" not in instrument.view.value.metadata_schema["properties"]
    seen: list[tuple[bool, bool]] = []
    instrument.view.subscribe(
        lambda view: seen.append(
            ("chamber" in view.metadata_schema["properties"], "chamber" in view.state.plan[0].metadata)
        )
    )

    await instrument.set_metadata_class(_SubjectMetadata)

    schema = instrument.view.value.metadata_schema
    assert schema["properties"]["subject_id"]["isKey"] is True
    assert schema["properties"]["chamber"] == {"$ref": "#/$defs/_Chamber", "isAnnotation": False}
    assert seen[-1] == (True, True)
    assert all(schema == plan for schema, plan in seen)  # never the new schema with the old plan, nor the reverse


async def test_each_required_metadata_field_left_empty_is_a_problem_at_its_field(instrument: _Bench) -> None:
    await _with_task(instrument)
    await instrument.set_metadata_class(_SubjectMetadata)  # a task with empty required fields is still accepted
    fields = {"experimenters": ["ana"], "chamber": {"medium": " "}, "spare": {"medium": ""}}
    await instrument._update_task_metadata("brain", fields)

    problems = instrument._metadata_problems()

    assert [(problem.loc, problem.msg) for problem in problems] == [
        (("plan", 0, "metadata", "subject_id"), "brain: Subject id is empty."),
        (("plan", 0, "metadata", "chamber", "medium"), "brain: Medium is empty."),
        (("plan", 0, "metadata", "spare", "medium"), "brain: Medium is empty."),
    ]
    await instrument._update_task_metadata(
        "brain", {"subject_id": "M-2816", "chamber": {"medium": "oil"}, "spare": None}
    )
    assert not instrument._metadata_problems()


def test_a_metadata_class_names_its_key_field_and_has_at_most_1() -> None:
    assert _SubjectMetadata.key_field() == "subject_id"
    assert _LabMetadata.key_field() is None
    with pytest.raises(TypeError, match="more than 1 key field"):
        type(
            "_TwoKeys",
            (ExperimentMetadata,),
            {"__annotations__": {"a": str, "b": str}, "a": key(default=""), "b": key(default="")},
        )


async def test_metadata_of_a_missing_task_is_not_found(instrument: _Bench) -> None:
    with pytest.raises(NotFoundError, match="No task 'brain'"):
        await instrument._update_task_metadata("brain", {"notes": "x"})


async def test_changing_the_metadata_form_keeps_what_fits_and_can_be_undone(instrument: _Bench) -> None:
    await _with_task(instrument)
    await instrument._update_task_metadata("brain", {"notes": "left hemisphere"})

    await instrument.set_metadata_class(_LabMetadata)
    assert _metadata(instrument) == {"notes": "left hemisphere", "operator": ""}
    assert instrument.view.value.history.undo_label == "Change the metadata form"

    await instrument.undo()
    assert instrument.view.value.state.metadata_cls is ExperimentMetadata
    assert _metadata(instrument) == {"notes": "left hemisphere"}


async def test_the_default_state_is_saved_and_restored(instrument: _Bench) -> None:
    await instrument.set_metadata_class(_LabMetadata)
    await instrument.save_as_default_state()
    assert instrument.view.value.default_state.metadata_cls is _LabMetadata

    await instrument.set_metadata_class(ExperimentMetadata)
    await instrument.restore_default_state()
    assert instrument.view.value.state.metadata_cls is _LabMetadata

    await instrument.undo()
    assert instrument.view.value.state.metadata_cls is ExperimentMetadata


async def test_restoring_the_metadata_form_keeps_the_metadata_that_fits(instrument: _Bench) -> None:
    await instrument.save_as_default_state()
    await _with_task(instrument)
    await instrument.set_metadata_class(_LabMetadata)
    await instrument._update_task_metadata("brain", {"notes": "left hemisphere", "operator": "ana"})

    await instrument.restore_default_state()
    assert instrument.view.value.state.metadata_cls is ExperimentMetadata
    assert _metadata(instrument) == {"notes": "left hemisphere"}

    await instrument.undo()
    assert _metadata(instrument) == {"notes": "left hemisphere", "operator": "ana"}


async def test_an_activity_that_holds_the_state_refuses_an_edit(instrument: _Bench) -> None:
    await _with_task(instrument)
    scheduler = instrument._scheduler
    async with scheduler.run("start a capture", requires=()):
        await scheduler.start(ActivityInfo(kind="capture"), {instrument._store}, stop=_nothing)

    with pytest.raises(ActivityBusyError, match="Update task metadata is not possible while capture is running"):
        await instrument._update_task_metadata("brain", {"notes": "left hemisphere"})


def _main(instrument: _Bench) -> tuple[str | None, str]:
    profile = instrument.view.value.state.profiles["main"]
    return profile.label, profile.desc


def _undo_label(instrument: _Bench) -> str | None:
    return instrument.view.value.history.undo_label


async def test_an_edit_inside_an_edit_joins_it_as_1_undo_step(instrument: _Bench) -> None:
    await instrument.label_main("Main", "the only profile")
    assert _main(instrument) == ("Main", "the only profile")
    assert _undo_label(instrument) == "Label main"

    await instrument.undo()
    assert _main(instrument) == (None, "")
    assert _undo_label(instrument) is None
    await instrument.redo()
    assert _main(instrument) == ("Main", "the only profile")


async def test_an_edit_that_raises_puts_back_what_it_saved(instrument: _Bench) -> None:
    with pytest.raises(RuntimeError, match="after the save"):
        await instrument.label_main("Main", "the only profile", fail=RuntimeError("after the save"))
    assert _main(instrument) == (None, "")
    assert _undo_label(instrument) is None


async def test_an_edit_inside_an_edit_that_is_refused_puts_back_the_outer_change(instrument: _Bench) -> None:
    untyped: Any = 5  # what a caller with no types can send
    with pytest.raises(RejectedError):
        await instrument.label_main("Main", untyped)
    assert _main(instrument) == (None, "")
    assert _undo_label(instrument) is None


async def test_a_device_that_does_not_exist_is_not_found(instrument: _Bench) -> None:
    with pytest.raises(NotFoundError, match="Device 'nope' not found"):
        await instrument.set_device_properties("nope", {"power": 1.0})


_BASIC_RIG: dict[str, Any] = {
    **_RIG,
    "parts": {"objective": {"target": "vxl.parts.Objective", "magnification": 10}},
    "optics": {
        "laser_488": {"to": "specimen"},
        "specimen": {"to": "objective"},
        "objective": {"to": "camera"},
        "camera": {"width": {"y": 1}, "height": {"x": -1}},
    },
}
"""The bench rig with an objective, so the base state's rules hold: each camera's path has a magnification."""


def _basic(tmp_path: Path) -> BasicInstrument:
    """A basic instrument on the bench rig with an objective, with the base state and its rules, not opened."""
    state = InstrumentState.model_validate(_DEFAULT)
    folder = InstrumentFolder(
        tmp_path,
        BasicInstrument,
        FolderFile(data=_BASIC_RIG, model=bench(_BASIC_RIG)),
        FolderFile(data=None, model=state),
        FolderFile(data=None),
        Problems(),
    )
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    return BasicInstrument(folder, records=records, system=system)


def test_a_basic_instrument_offers_the_base_operations_and_its_profile_update() -> None:
    assert set(BasicInstrument.operations) == set(_Bench.operations) | {
        "update_profile",
        "add_task",
        "update_task",
        "update_task_metadata",
        "remove_tasks",
        "reorder_tasks",
    }
    update = BasicInstrument.operations["update_profile"]
    assert (update.intent, update.resource, update.key) == ("update", "profiles", "profile_id")
    assert set(update.params["properties"]) == {"profile_id", "label", "desc", "tuning_knobs"}


async def test_a_basic_instrument_updates_a_profile_as_1_undo_step(tmp_path: Path) -> None:
    basic = _basic(tmp_path)

    await basic.execute("update_profile", {"profile_id": "main", "label": "Main", "desc": "the only profile"})
    profile = basic.view.value.state.profiles["main"]
    assert (profile.label, profile.desc) == ("Main", "the only profile")

    await basic.execute("undo", {})
    profile = basic.view.value.state.profiles["main"]
    assert (profile.label, profile.desc) == (None, "")


async def test_a_basic_instrument_refuses_unknown_profiles_and_fields(tmp_path: Path) -> None:
    basic = _basic(tmp_path)

    with pytest.raises(NotFoundError, match="No profile 'other'"):
        await basic.execute("update_profile", {"profile_id": "other", "label": "x"})
    with pytest.raises(RejectedError, match="spacing"):
        await basic.execute("update_profile", {"profile_id": "main", "spacing": 2.0})
