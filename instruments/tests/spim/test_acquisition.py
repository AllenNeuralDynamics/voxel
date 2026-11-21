"""Acquisitions on simulated devices that pass their trigger edges along the rig's wires."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from ome_zarr_writer import ScaleLevel
from vxl_instruments.spim.instrument import AcquisitionInfo, Microscope
from vxl_instruments.spim.task import SPIMTask

from vxl.instrument.folder import InstrumentFolder
from vxl.records import Acquisition, Records
from vxl.station.errors import RejectedError
from vxl.storage import StorageSpec
from vxl.system import System

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


async def _open(data: dict[str, Any], tmp_path: Path, *, depth_um: float = 4) -> Microscope:
    folder = InstrumentFolder.create(template(data), "left", tmp_path)
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / "data" / spec.path)
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    microscope = Microscope(folder, records=records, system=system)
    await microscope.open()
    region = {"outline": {"kind": "explicit_points", "points": [{"x": 0, "y": 0}]}, "bounds": [0, depth_um]}
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
    assert stepping.view.value.power_mode == "full"
    position = (await stepping.stage_position())["z"]
    assert position == pytest.approx(stored.visits[0].images()["camera"].frames_total, abs=0.5)


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
            written.append(visit.images()["camera"].frames_written)

    unsubscribe = microscope._records.acquisitions.subscribe(seen)
    try:
        await microscope.start_acquisition(_STORAGE, "ana")
        await _finish(microscope)
    finally:
        unsubscribe()
        await microscope.close()
    assert any(0 < frames < 20 for frames in written), written
