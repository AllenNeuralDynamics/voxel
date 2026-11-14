from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from vxl_records import SQLiteRecords
from vxlib.problems import Problems

from vxl.core.errors import BusyError, RejectedError, StartupError
from vxl.core.instrument.base import Instrument
from vxl.core.instrument.config import InstrumentConfig, InstrumentState
from vxl.core.instrument.folder import InstrumentFolder
from vxl.core.instrument.gate import Activity
from vxl.metadata import ExperimentMetadata
from vxl.system import System

from .support import bench

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vxl.core.views import DeviceView

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
            "target": "vxl.devices.laser.simulated.SimulatedLaser",
            "init": {"wavelength": 488, "source_enable_delay_s": 0},
        },
        "x_axis": {"target": _AXIS, "init": {"lower": 0, "upper": 1000, "speed": 100_000}},
        "y_axis": {"target": _AXIS, "init": {"lower": 0, "upper": 1000, "speed": 100_000}},
        "z_axis": {"target": _AXIS, "init": {"lower": 0, "upper": 1000, "speed": 100_000}},
    },
    "stage": {"x": "x_axis", "y": "y_axis", "z": "z_axis"},
    "optics": {
        "laser_488": {"to": "sample"},
        "sample": {"to": "camera"},
        "camera": {"width": {"y": 1}, "height": {"x": -1}},
    },
}


class _State(InstrumentState, frozen=True):
    def problems(self, config: InstrumentConfig) -> Problems:
        """No rules of its own: only the rig's."""
        return config.problems()


class _Bench(Instrument[InstrumentConfig, _State]):
    """The smallest kind of instrument: the base config and a state with no rules."""


def _folder(
    tmp_path: Path, rig: dict[str, Any], kind: type[_Bench] | None = None
) -> InstrumentFolder[InstrumentConfig, _State]:
    """A folder as :meth:`InstrumentFolder.read` gives it, with no files on disk."""
    return InstrumentFolder(tmp_path, kind, bench(rig), _State(), None, Problems())


def _instrument(tmp_path: Path, rig: dict[str, Any]) -> _Bench:
    records = SQLiteRecords(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
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
    views = instrument.device_views.value
    kinds = {uid: view.interface.kind for uid, view in views.items()}

    assert set(kinds) == set(_RIG["devices"])
    assert (kinds["camera"], kinds["laser_488"], kinds["x_axis"]) == ("camera", "laser", "linear_axis")
    assert views["laser_488"].props


async def test_a_property_set_is_written_and_shown(instrument: _Bench) -> None:
    sent: list[Mapping[str, DeviceView]] = []
    instrument.device_views.subscribe(sent.append)

    results = await instrument.set_device_properties("laser_488", {"source_power_setpoint_mw": 12.5})

    assert results.ok["source_power_setpoint_mw"].value == 12.5
    assert sent
    assert instrument.device_views.value["laser_488"].props["source_power_setpoint_mw"].value == 12.5


async def test_the_views_are_empty_after_close(instrument: _Bench) -> None:
    await instrument.close()

    assert instrument.device_views.value == {}


async def test_a_device_command_runs(instrument: _Bench) -> None:
    result = await instrument.execute_device_command("laser_488", "output_disable")

    assert result.is_ok


async def test_move_stage_moves_only_the_given_axes(instrument: _Bench) -> None:
    await instrument.move_stage(x=100, z=250, wait=True)

    stage = instrument._hal.stage
    positions = {axis: await stage[axis].position.get() for axis in ("x", "y", "z")}
    assert positions == {"x": 100, "y": 0, "z": 250}


async def test_a_hub_command_is_refused_while_an_activity_holds_a_device_on_it(
    instrument: _Bench,
) -> None:
    gate = instrument._gate
    async with gate.command("start a calibration", touches=()):
        await gate.begin(Activity(kind="calibration"), {"daq"})

    with pytest.raises(BusyError, match="while calibration is running"):
        await instrument.execute_device_command("daq_hub", "close")
    assert (await instrument.execute_device_command("laser_488", "output_disable")).is_ok


async def test_a_device_of_the_wrong_kind_stops_the_start(tmp_path: Path) -> None:
    rig = {**_RIG, "stage": {"x": "daq", "y": "y_axis", "z": "z_axis"}}
    instrument = _instrument(tmp_path, rig)

    with pytest.raises(StartupError) as caught:
        await instrument.open()

    assert caught.value.problems.codes() == ["rig.device.not_linear_axis"]


async def test_a_device_with_2_roles_is_checked_for_each(tmp_path: Path) -> None:
    rig = {**_RIG, "stage": {"x": "camera", "y": "y_axis", "z": "z_axis"}}
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
    return InstrumentFolder.create({"rig": {**_RIG, "target": target}, "default": {}}, "bench", tmp_path)


def test_read_finds_the_kind_and_reads_the_files(tmp_path: Path) -> None:
    folder = _create(tmp_path, f"{__name__}._Bench")

    assert folder.ok, folder.problems
    assert folder.kind is _Bench
    assert isinstance(folder.default, _State)
    assert InstrumentFolder.read(folder.home) == folder


def test_read_gives_a_problem_for_a_target_it_cannot_import(tmp_path: Path) -> None:
    assert _create(tmp_path, "nowhere.Kind").problems.codes() == ["rig.target"]
    assert InstrumentFolder.read(tmp_path / "empty.voxel").problems.codes() == ["rig.missing"]


def test_the_folder_builds_the_instrument_of_its_kind(tmp_path: Path) -> None:
    folder = _create(tmp_path, f"{__name__}._Bench")
    records = SQLiteRecords(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)

    assert type(folder.instrument(records=records, system=system)) is _Bench

    class _Other(Instrument[InstrumentConfig, _State]):
        pass

    with pytest.raises(TypeError, match="is run by _Bench, not by _Other"):
        _Other(folder, records=records, system=system)


class _LabMetadata(ExperimentMetadata):
    operator: str = ""


async def test_a_metadata_edit_can_be_undone_and_redone(instrument: _Bench) -> None:
    await instrument.update_metadata(notes="left hemisphere")
    assert instrument.state.value.metadata["notes"] == "left hemisphere"
    assert instrument.history.value.undo_label == "Update metadata"

    await instrument.undo()
    assert instrument.state.value.metadata.get("notes", "") == ""
    await instrument.redo()
    assert instrument.state.value.metadata["notes"] == "left hemisphere"


async def test_metadata_that_does_not_fit_its_form_is_rejected_at_its_field(instrument: _Bench) -> None:
    with pytest.raises(RejectedError) as caught:
        await instrument.update_metadata(weight=12)

    assert [problem.loc for problem in caught.value.problems] == [("metadata", "weight")]
    assert instrument.history.value.undo_label is None


async def test_changing_the_metadata_form_keeps_what_fits_and_can_be_undone(instrument: _Bench) -> None:
    await instrument.update_metadata(notes="left hemisphere")

    await instrument.set_metadata_class(_LabMetadata)
    assert instrument.state.value.metadata == {"notes": "left hemisphere", "operator": ""}
    assert instrument.history.value.undo_label == "Change the metadata form"

    await instrument.undo()
    assert instrument.state.value.metadata_cls is ExperimentMetadata
    await instrument.undo()
    assert instrument.state.value.metadata.get("notes", "") == ""


async def test_the_default_state_is_saved_and_restored(instrument: _Bench) -> None:
    await instrument.set_metadata_class(_LabMetadata)
    await instrument.save_as_default_state()
    assert instrument.default_state.value.metadata_cls is _LabMetadata

    await instrument.set_metadata_class(ExperimentMetadata)
    await instrument.restore_default_state()
    assert instrument.state.value.metadata_cls is _LabMetadata

    await instrument.undo()
    assert instrument.state.value.metadata_cls is ExperimentMetadata


async def test_restoring_the_metadata_form_keeps_the_metadata_that_fits(instrument: _Bench) -> None:
    await instrument.update_metadata(notes="left hemisphere")
    await instrument.save_as_default_state()
    await instrument.set_metadata_class(_LabMetadata)
    await instrument.update_metadata(operator="ana")

    await instrument.restore_default_state()
    assert instrument.state.value.metadata_cls is ExperimentMetadata
    assert instrument.state.value.metadata == {"notes": "left hemisphere"}

    await instrument.undo()
    assert instrument.state.value.metadata == {"notes": "left hemisphere", "operator": "ana"}


async def test_an_activity_that_holds_the_state_refuses_an_edit(instrument: _Bench) -> None:
    gate = instrument._gate
    async with gate.command("start a capture", touches=()):
        await gate.begin(Activity(kind="capture"), {instrument._store})

    with pytest.raises(BusyError, match="Unable to update metadata while capture is running"):
        await instrument.update_metadata(notes="left hemisphere")
