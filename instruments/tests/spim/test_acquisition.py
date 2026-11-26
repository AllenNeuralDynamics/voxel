"""Acquisitions on simulated devices that pass their trigger edges along the rig's wires."""

import asyncio
import copy
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from ome_zarr_writer import ScaleLevel
from rigup.device.handle import PropView
from vxl_drivers.metadata import ExaspimMetadata
from vxl_instruments.spim.instrument import AcquisitionInfo, Microscope
from vxl_instruments.spim.plan import PlannedTask, Unplanned
from vxl_instruments.spim.task import SPIMTask
from vxlib.issues import Level

from vxl.devices.camera import handle as camera_handle
from vxl.devices.camera.area import AreaCameraController
from vxl.instrument.folder import InstrumentFolder
from vxl.records import Acquisition, Records
from vxl.station.config import StationInfo
from vxl.station.errors import RejectedError, StaleError
from vxl.station.station import SessionInfo, SessionView, StationStatus, StationView
from vxl.storage import StorageSpec
from vxl.system import System
from vxl.web.station.topics import StationTopics

from .support import simulated, template

_STORAGE = StorageSpec(path=PurePosixPath("runs/1"))


def _wired(data: dict[str, Any]) -> dict[str, Any]:
    """``data`` on simulated devices that share the rig's wires: a small camera that waits for its trigger, a
    generator that plays on the wires, and stage axes that step on pulses and send them while they sweep."""
    data = simulated(data)
    devices = data["devices"]
    devices["sim_wiring"] = {"target": "vxl.devices.simulated.SimulatedWiring", "init": {"wiring": data["wiring"]}}
    devices["ao_main"]["init"]["wiring"] = "sim_wiring"
    devices["camera"]["init"] |= {
        "frame_source": {"sensor_size_px": {"x": 64, "y": 64}, "pixel_size_um": {"x": 6.5, "y": 6.5}},
        "wiring": "sim_wiring",
        "trigger_timeout_s": 2,
    }
    for axis in ("x_axis", "y_axis", "z_axis"):
        devices[axis]["init"]["wiring"] = "sim_wiring"
    return data


def _sweep_z(data: dict[str, Any]) -> dict[str, Any]:
    """``data`` with stage Z sweeping, its pulses starting each cycle of the generator."""
    data["wiring"]["z_axis"] = {"z_pulse": {"pin": "ttl_out", "to": ["ao_main/pfi0"], "kind": "digital"}}
    # Simulated threads can be late by several ms, and a generator misses a pulse while it plays a cycle: a wide margin.
    data["scan"] = {"axis": "z", "motion": "sweep", "pacer": "z_axis", "margin": "30 %"}
    return data


async def _open(
    data: dict[str, Any], tmp_path: Path, *, depth_um: float = 4, points: tuple[tuple[float, float], ...] = ((0, 0),)
) -> Microscope:
    folder = InstrumentFolder.create(template(data), "left", tmp_path)
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / "data" / spec.path)
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    microscope = Microscope(folder, records=records, system=system)
    await microscope.open()
    outline = {"kind": "explicit_points", "points": [{"x": x, "y": y} for x, y in points]}
    region = {"outline": outline, "bounds": [0, depth_um]}
    task = SPIMTask.complete({"id": "brain", "region": region, "profiles": ["gfp"]}, microscope.view.value.state.task)
    await microscope.add_task(task)
    await microscope.update_writer_settings(max_level=ScaleLevel.L2, batch_frames=4)  # a visit takes 2 batches
    return microscope


@pytest.fixture
async def stepping(config_data: dict[str, Any], tmp_path: Path) -> AsyncIterator[Microscope]:
    microscope = await _open(_wired(config_data), tmp_path)
    yield microscope
    await microscope.close()


@pytest.fixture
async def sweeping(config_data: dict[str, Any], tmp_path: Path) -> AsyncIterator[Microscope]:
    microscope = await _open(_wired(_sweep_z(config_data)), tmp_path)
    yield microscope
    await microscope.close()


async def _finish(microscope: Microscope) -> None:
    async with asyncio.timeout(20):
        while True:  # the run ends in the background: its activity is polled
            if not microscope.view.value.activities:
                return
            await asyncio.sleep(0.05)


async def test_a_step_scan_takes_every_frame_and_records_a_completed_visit(stepping: Microscope) -> None:
    acquisition_id = await stepping.start_acquisition(_STORAGE, "ana")
    assert [activity.kind for activity in stepping.view.value.activities] == ["acquisition"]
    await _finish(stepping)

    stored = await stepping._records.acquisitions.get(acquisition_id)
    assert stored.status == "completed"
    assert [visit.image_status("camera") for visit in stored.visits] == ["completed"]
    location = stored.visits[0].images()["camera"].locations[0]
    assert "000000/gfp/gfp/camera" in str(location.model_dump())  # visit, profile, channel, camera
    assert stored.visits[0].location_status("camera") == "available"
    assert stored.visits[0].images()["camera"].closed_at is not None
    assert stepping.view.value.power_mode == "full"
    position = (await stepping.stage_position())["z"]
    assert position == pytest.approx(stored.visits[0].images()["camera"].frames_total, abs=0.5)


async def test_an_image_whose_close_fails_is_failed_at_its_location(
    stepping: Microscope, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(controller: AreaCameraController) -> None:
        raise OSError(f"the disk of {controller.device.id} is full")

    monkeypatch.setattr(AreaCameraController, "_close_image", broken)
    acquisition_id = await stepping.start_acquisition(_STORAGE, "ana")
    await _finish(stepping)

    stored = await stepping._records.acquisitions.get(acquisition_id)
    visit = stored.visits[0]
    assert visit.status == "failed"
    assert "the disk of camera is full" in visit.failures[0].msg
    assert (visit.image_status("camera"), visit.location_status("camera")) == ("completed", "failed")


async def test_a_stop_while_the_images_close_lets_them_close_and_records_them_available(
    stepping: Microscope, monkeypatch: pytest.MonkeyPatch
) -> None:
    close = AreaCameraController._close_image
    closing = asyncio.Event()

    async def slow(controller: AreaCameraController) -> None:
        closing.set()
        await asyncio.sleep(1.0)
        await close(controller)

    monkeypatch.setattr(AreaCameraController, "_close_image", slow)
    acquisition_id = await stepping.start_acquisition(_STORAGE, "ana")
    async with asyncio.timeout(20):
        await closing.wait()
    await stepping.stop_acquisition()

    stored = await stepping._records.acquisitions.get(acquisition_id)
    visit = stored.visits[0]
    assert (stored.status, visit.status) == ("cancelled", "cancelled")
    assert (visit.image_status("camera"), visit.location_status("camera")) == ("completed", "available")


async def test_a_scan_that_fails_keeps_its_frame_count_and_its_closed_image(
    stepping: Microscope, monkeypatch: pytest.MonkeyPatch
) -> None:
    wait = Microscope._wait_for_batches
    batches: list[int] = []

    async def fails_after_the_first(microscope: Microscope, cameras: Any, numbers: Any) -> None:
        await wait(microscope, cameras, numbers)
        batches.append(1)
        raise RuntimeError("the stage faulted")

    monkeypatch.setattr(Microscope, "_wait_for_batches", fails_after_the_first)
    acquisition_id = await stepping.start_acquisition(_STORAGE, "ana")
    await _finish(stepping)

    stored = await stepping._records.acquisitions.get(acquisition_id)
    visit = stored.visits[0]
    assert [failure.msg for failure in visit.failures] == ["RuntimeError: the stage faulted"]
    assert visit.images()["camera"].frames_collected == 4  # the first batch
    assert (visit.image_status("camera"), visit.location_status("camera")) == ("partial", "available")


async def test_a_camera_that_stops_answering_while_its_image_closes_fails_the_image_and_does_not_hang(
    stepping: Microscope, monkeypatch: pytest.MonkeyPatch
) -> None:
    gone = asyncio.Event()
    read = PropView.get

    async def hangs(_controller: AreaCameraController) -> None:
        gone.set()
        await asyncio.sleep(3600)

    async def get(view: PropView[Any]) -> Any:
        if gone.is_set() and view.name == "capture":
            raise ConnectionError("transport closed")
        return await read(view)

    monkeypatch.setattr(AreaCameraController, "_close_image", hangs)
    monkeypatch.setattr(PropView, "get", get)
    monkeypatch.setattr(camera_handle, "_RECHECK_S", 0.05)
    acquisition_id = await stepping.start_acquisition(_STORAGE, "ana")
    await _finish(stepping)

    stored = await stepping._records.acquisitions.get(acquisition_id)
    visit = stored.visits[0]
    assert visit.status == "failed"
    assert "camera stopped answering" in visit.failures[0].msg
    assert visit.location_status("camera") == "failed"


async def test_a_sweep_takes_every_frame_on_the_stage_pulses(sweeping: Microscope) -> None:
    acquisition_id = await sweeping.start_acquisition(_STORAGE, "ana")
    await _finish(sweeping)

    stored = await sweeping._records.acquisitions.get(acquisition_id)
    assert stored.status == "completed", stored.visits[0].failures
    assert [visit.image_status("camera") for visit in stored.visits] == ["completed"]


async def test_during_a_run_edits_and_device_actions_are_refused_and_a_stop_cancels_it(stepping: Microscope) -> None:
    acquisition_id = await stepping.start_acquisition(_STORAGE, "ana")
    info = stepping.view.value.activities[0]
    assert isinstance(info, AcquisitionInfo)
    assert info.acquisition_id == acquisition_id

    with pytest.raises(RejectedError, match="already running"):
        await stepping.start_acquisition(_STORAGE, "ana")
    with pytest.raises(Exception, match="while acquisition is running"):
        await stepping.update_profile("gfp", spacing=2.0)
    with pytest.raises(Exception, match="while acquisition is running"):
        await stepping.execute_device_command("fw", "move_to", ["RFP"])
    with pytest.raises(Exception, match="while acquisition is running"):
        await stepping.set_power_mode("dim")

    await stepping.stop_acquisition()
    assert stepping.view.value.activities == ()
    stored = await stepping._records.acquisitions.get(acquisition_id)
    assert stored.status == "cancelled"


async def test_a_task_with_empty_required_metadata_refuses_the_start(stepping: Microscope) -> None:
    await stepping.set_metadata_class(ExaspimMetadata)

    with pytest.raises(RejectedError, match="Subject id is empty") as caught:
        await stepping.start_acquisition(_STORAGE, "ana")

    assert [problem.loc for problem in caught.value.problems] == [("plan", 0, "metadata", "subject_id")]
    assert stepping.view.value.activities == ()


async def test_a_task_left_outside_a_narrowed_specimen_range_stops_only_the_start(
    config_data: dict[str, Any], tmp_path: Path
) -> None:
    data = _wired(config_data)
    first = await _open(copy.deepcopy(data), tmp_path)
    await first.close()
    data["stage"]["x"]["specimen"] = [100, 200]
    folder = InstrumentFolder.create(template(data), "right", tmp_path)
    shutil.copy(tmp_path / "left.voxel" / "state.json", folder.home / "state.json")
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / "data" / spec.path)
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    microscope = Microscope(InstrumentFolder.read(folder.home), records=records, system=system)
    await microscope.open()
    try:
        alerts = [(alert.code, alert.level) for alert in microscope.view.value.alerts]
        with pytest.raises(RejectedError) as caught:
            await microscope.start_acquisition(_STORAGE, "ana")
        await microscope.update_profile("gfp", spacing=2.0)
    finally:
        await microscope.close()

    assert ("task.region.outside_specimen", Level.ERROR) in alerts
    assert [problem.code for problem in caught.value.problems] == ["task.region.outside_specimen"]


async def test_a_run_past_the_stage_limits_refuses_the_start(config_data: dict[str, Any], tmp_path: Path) -> None:
    microscope = await _open(_wired(config_data), tmp_path, points=((0, 60_000),))
    try:
        with pytest.raises(RejectedError) as caught:
            await microscope.start_acquisition(_STORAGE, "ana")
    finally:
        await microscope.close()

    (problem,) = caught.value.problems
    assert (problem.code, problem.loc) == ("task.plan.outside_limits", ("plan", 0, "region"))
    assert problem.msg == (
        "brain: the stage would go to y 60000.0..60000.0 µm, past the y-axis limits -50000..50000 µm."
    )


async def test_the_start_runs_the_plan_that_was_shown_and_refuses_one_that_changed_since(stepping: Microscope) -> None:
    shown = stepping.view.value.plan_fingerprint
    await stepping.update_profile("gfp", spacing=2.0)
    view = stepping.view.value
    planned = view.planned_tasks["brain"]
    assert isinstance(planned, PlannedTask)
    assert (planned.scan.frames, len(planned.stops)) == ({"gfp": 3}, 1)
    assert view.plan_fingerprint not in (None, shown)

    with pytest.raises(StaleError):
        await stepping.start_acquisition(_STORAGE, "ana", shown)
    acquisition_id = await stepping.start_acquisition(_STORAGE, "ana", view.plan_fingerprint)
    await _finish(stepping)

    stored = await stepping._records.acquisitions.get(acquisition_id)
    assert stored.visits[0].images()["camera"].frames_total == 3


async def test_the_plan_is_1_topic_for_each_task_and_each_footprint(stepping: Microscope) -> None:
    session = SessionView(info=SessionInfo(id=uuid.uuid4(), instrument_name="left"), instrument=stepping.view.value)
    view = StationView(status=StationStatus.ACTIVE, session=session)
    topics = StationTopics.view_topics(StationInfo(id=uuid.uuid4(), name="s"), view)

    (footprint_id,) = stepping.view.value.footprints
    task, footprint = topics["instrument.planned_tasks.brain"], topics[f"instrument.footprints.{footprint_id}"]
    assert isinstance(task, dict)
    assert isinstance(footprint, dict)
    assert task["stops"] == [[0, 0, 0]]
    assert footprint["size_px"] == {"rows": 64, "columns": 64}
    assert isinstance(topics["instrument.plan_fingerprint"], str)
    assert "instrument.planned_tasks" not in topics
    assert "instrument.remote_stores" in topics  # a mapping without the mark stays 1 topic


async def test_a_task_saved_before_the_open_is_planned_once_the_cameras_report(
    config_data: dict[str, Any], tmp_path: Path
) -> None:
    first = await _open(_wired(config_data), tmp_path)
    shown = first.view.value.plan_fingerprint
    await first.close()

    folder = InstrumentFolder.read(next(tmp_path.rglob("rig.yaml")).parent)
    records = Records(tmp_path / "again.sqlite3", resolve_root=lambda spec: tmp_path / "data" / spec.path)
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    again = Microscope(folder, records=records, system=system)
    assert isinstance(again.view.value.planned_tasks["brain"], Unplanned)  # no camera has reported yet
    await again.open()
    try:
        assert isinstance(again.view.value.planned_tasks["brain"], PlannedTask)
        assert again.view.value.plan_fingerprint == shown
    finally:
        await again.close()


async def test_a_step_scan_paced_by_the_program_takes_every_frame(config_data: dict[str, Any], tmp_path: Path) -> None:
    config_data["scan"] = {"axis": "z", "motion": "step", "pacer": "software"}
    microscope = await _open(_wired(config_data), tmp_path)
    try:
        acquisition_id = await microscope.start_acquisition(_STORAGE, "ana")
        await _finish(microscope)
        stored = await microscope._records.acquisitions.get(acquisition_id)
    finally:
        await microscope.close()
    assert stored.status == "completed", stored.visits[0].failures
    assert [visit.image_status("camera") for visit in stored.visits] == ["completed"]


async def test_progress_reaches_the_record_while_a_visit_runs(config_data: dict[str, Any], tmp_path: Path) -> None:
    microscope = await _open(_wired(config_data), tmp_path, depth_um=19)  # 20 frames of 100 ms: longer than 1 save
    written: list[int] = []

    def seen(acquisition: Acquisition) -> None:
        visit = acquisition.visits[0]
        if visit.result is None:
            written.append(visit.images()["camera"].frames_collected)

    unsubscribe = microscope._records.acquisitions.subscribe(seen)
    try:
        await microscope.start_acquisition(_STORAGE, "ana")
        await _finish(microscope)
    finally:
        unsubscribe()
        await microscope.close()
    assert any(0 < frames < 20 for frames in written), written


async def test_an_alternating_scan_steps_every_2nd_stop_back_down(config_data: dict[str, Any], tmp_path: Path) -> None:
    config_data["default"]["task"]["path"]["scan"] = {"z": "alternate"}
    microscope = await _open(_wired(config_data), tmp_path, points=((0, 0), (500, 0)))
    try:
        acquisition_id = await microscope.start_acquisition(_STORAGE, "ana")
        await _finish(microscope)
        stored = await microscope._records.acquisitions.get(acquisition_id)
        position = (await microscope.stage_position())["z"]
    finally:
        await microscope.close()
    assert [visit.status for visit in stored.visits] == ["completed", "completed"]
    steps = [visit.images()["camera"].transform.steps[0].z for visit in stored.visits]
    assert steps == [1.0, -1.0]
    assert position == pytest.approx(-1.0, abs=0.5)  # the 2nd stop steps from 4 µm down, 1 step past its last frame
