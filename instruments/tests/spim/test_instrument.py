"""What the SPIM microscope adds to every instrument: spacing and writer settings, camera regions, the preview, and
its live frames. What every instrument does is tested in ``tests/station/test_instrument.py``."""

import asyncio
import copy
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from ome_zarr_writer import WriterSettings
from pydantic import BaseModel
from vxl_instruments.spim.config import SPIMProfile
from vxl_instruments.spim.instrument import Microscope
from vxl_instruments.spim.state import SPIMProfileFields, WriterFields
from vxl_instruments.spim.task import SPIMTask, SPIMTaskFields

from vxl.devices.camera import AreaROI
from vxl.live import LiveSourceEmission, LiveViewport, live_source_header
from vxl.records import Records
from vxl.station.errors import RejectedError, StartupError
from vxl.station.instrument.folder import InstrumentFolder
from vxl.system import System

from .support import objective_turret, simulated, template, two_cameras


def _microscope(config_data: dict[str, Any], tmp_path: Path) -> Microscope:
    folder = InstrumentFolder.create(template(config_data), "left", tmp_path)
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    return Microscope(folder, records=records, system=system)


@pytest.fixture
def microscope(config_data: dict[str, Any], tmp_path: Path) -> Microscope:
    return _microscope(config_data, tmp_path)


async def test_writer_spacing_and_profile_detail_edits_can_be_undone(microscope: Microscope) -> None:
    await microscope.update_writer_settings(shard_z_chunks=4, target_shard_gb=2.0)
    await microscope.update_profile("gfp", spacing=2.5)
    await microscope.update_profile("gfp", label="GFP", desc="green")
    state = microscope.view.value.state
    assert (state.writer.shard_z_chunks, state.profiles["gfp"].spacing) == (4, 2.5)
    assert (state.profiles["gfp"].label, state.profiles["gfp"].desc) == ("GFP", "green")

    for _ in range(3):
        await microscope.undo()
    assert microscope.view.value.state == microscope.view.value.default_state


@pytest.mark.parametrize(
    ("profile_id", "spacing", "loc"),
    [("rfp", 2.0, ("profiles", "rfp")), ("gfp", -1, ("profiles", "gfp", "spacing"))],
)
async def test_a_spacing_edit_is_refused_at_its_path(
    microscope: Microscope, profile_id: str, spacing: float, loc: tuple[str, ...]
) -> None:
    with pytest.raises(RejectedError) as caught:
        await microscope.update_profile(profile_id, spacing=spacing)
    assert [problem.loc for problem in caught.value.problems] == [loc]
    assert microscope.view.value.history.undo_label is None


@pytest.mark.parametrize(
    ("fields", "model"), [(SPIMTaskFields, SPIMTask), (WriterFields, WriterSettings), (SPIMProfileFields, SPIMProfile)]
)
def test_each_field_list_names_fields_of_its_model(fields: type, model: type[BaseModel]) -> None:
    assert fields.__annotations__.keys() <= model.model_fields.keys()


@pytest.fixture
async def opened(config_data: dict[str, Any], tmp_path: Path) -> AsyncIterator[Microscope]:
    """An open microscope on simulated devices. Profile ``gfp`` sets the camera's exposure to 20 ms, ``slow`` to
    30 ms."""
    profiles = config_data["default"]["profiles"]
    gfp = profiles["gfp"]
    gfp["props"] = {"camera": {"exposure_time_ms": 20.0}}
    profiles["slow"] = copy.deepcopy(gfp) | {"props": {"camera": {"exposure_time_ms": 30.0}}}
    microscope = _microscope(simulated(config_data), tmp_path)
    await microscope.open()
    yield microscope
    await microscope.close()


async def _exposure(microscope: Microscope) -> float:
    results = await microscope.get_device_properties("camera", ["exposure_time_ms"])
    return results.results["exposure_time_ms"].unwrap().value


async def test_a_camera_region_is_saved_as_the_camera_snapped_it(opened: Microscope) -> None:
    applied = await opened.set_camera_region("camera", AreaROI(x=3, y=5, w=1001, h=999))
    assert opened.view.value.state.profiles["gfp"].fov["camera"] == applied

    full = await opened.set_camera_region("camera", None)
    assert (full.w, full.h) == (2048, 2048)
    assert "camera" not in opened.view.value.state.profiles["gfp"].fov


def _second_camera(data: dict[str, Any]) -> dict[str, Any]:
    """Add a switch after the filter wheel that sends the light to ``camera`` or to a second camera, ``camera2``.
    Every profile keeps ``camera``."""
    data["devices"]["det_switch"] = copy.deepcopy(data["devices"]["fw"])
    data["devices"]["det_switch"]["init"]["slots"] = {
        "0": {"label": "a", "position": 0},
        "1": {"label": "b", "position": 10},
    }
    data["devices"]["camera2"] = copy.deepcopy(data["devices"]["camera"])
    data["optics"].update(
        fw={"to": "det_switch"},
        det_switch={"to": {"a": "camera", "b": "camera2"}},
        camera2=copy.deepcopy(data["optics"]["camera"]),
    )
    data["default"]["profiles"]["gfp"]["positions"]["det_switch"] = "a"
    return data


async def test_a_region_on_a_camera_outside_the_active_profile_is_set_but_not_saved(
    config_data: dict[str, Any], tmp_path: Path
) -> None:
    microscope = _microscope(_second_camera(simulated(config_data)), tmp_path)
    await microscope.open()
    try:
        before = microscope.view.value.state
        applied = await microscope.set_camera_region("camera2", AreaROI(x=0, y=0, w=1024, h=1024))
        assert (applied.w, applied.h) == (1024, 1024)
        assert microscope.view.value.state == before
    finally:
        await microscope.close()


async def _live(microscope: Microscope) -> dict[str, object]:
    """What a preview has started: each camera's mode, if the laser is on, the generator's state, the activities."""
    hal = microscope._hal
    return {
        "cameras": {uid: (await camera.props.get_value("mode")) for uid, camera in hal.area_cameras.items()},
        "laser": await hal.device("laser").props.get_value("is_on"),
        "generator": await hal.signal_generators["ao_main"].state.get(),
        "activities": [activity.kind for activity in microscope.view.value.activities],
    }


async def test_a_preview_starts_and_stops_its_devices(opened: Microscope) -> None:
    await opened.start_preview()
    assert await _live(opened) == {
        "cameras": {"camera": "PREVIEW"},
        "laser": True,
        "generator": "running",
        "activities": ["preview"],
    }
    await opened.stop_preview()
    assert await _live(opened) == {
        "cameras": {"camera": "IDLE"},
        "laser": False,
        "generator": "loaded",
        "activities": [],
    }


async def test_a_laser_failsafe_during_a_preview_keeps_the_laser_off(opened: Microscope) -> None:
    await opened.start_preview()

    await opened.execute_device_command("laser", "off")

    live = await _live(opened)
    assert live["laser"] is False
    assert live["activities"] == ["preview"]
    await opened.stop_preview()


async def test_stop_ends_the_preview_and_runs_every_failsafe(opened: Microscope) -> None:
    await opened.start_preview()

    await opened.stop()

    live = await _live(opened)
    assert live["activities"] == []
    assert live["laser"] is False
    assert live["cameras"] == {"camera": "IDLE"}


async def test_a_preview_disarms_the_scan_axis(opened: Microscope) -> None:
    z = opened._hal.stage["z"]
    await z.arm_steps(1.0, 5, "ttl_in")
    await opened.start_preview()
    assert await z.scan_state.get() == "idle"
    await opened.stop_preview()


async def test_a_preview_restarts_around_a_profile_change(opened: Microscope) -> None:
    await opened.start_preview()
    await opened.select_profile("slow")
    assert (await _live(opened))["activities"] == ["preview"]
    assert await _exposure(opened) == pytest.approx(30.0)
    assert (await _live(opened))["cameras"] == {"camera": "PREVIEW"}
    await opened.stop_preview()


async def test_each_profile_keeps_its_preview_channels(config_data: dict[str, Any], tmp_path: Path) -> None:
    microscope = _microscope(two_cameras(simulated(config_data)), tmp_path)
    await microscope.open()
    try:
        await microscope.start_preview()
        assert microscope.view.value.preview_channels == ("camera",)
        await microscope.set_preview_channels(["camera_2"])
        assert (await _live(microscope))["cameras"] == {"camera": "IDLE", "camera_2": "PREVIEW"}
        await microscope.select_profile("rfp")
        assert microscope.view.value.preview_channels == ("camera",)
        await microscope.select_profile("gfp")
        assert microscope.view.value.preview_channels == ("camera_2",)
        assert (await _live(microscope))["cameras"] == {"camera": "IDLE", "camera_2": "PREVIEW"}
        with pytest.raises(RejectedError, match="no channel"):
            await microscope.set_preview_channels(["laser"])
    finally:
        await microscope.close()


async def test_a_line_camera_stops_the_opening(config_data: dict[str, Any], tmp_path: Path) -> None:
    data = simulated(config_data)
    data["devices"]["camera"] = {"target": "vxl.devices.camera.line.LineCamera"}
    del data["autosave"]["camera"]  # a line camera has no exposure to save yet
    microscope = _microscope(data, tmp_path)
    with pytest.raises(StartupError) as caught:
        await microscope.open()
    assert [(p.code, p.loc) for p in caught.value.problems] == [
        ("spim.camera.not_area", ("profiles", "gfp", "channels", "camera"))
    ]


async def test_live_frames_come_with_their_stage_position_and_old_streams_drop(
    config_data: dict[str, Any], tmp_path: Path
) -> None:
    microscope = _microscope(two_cameras(simulated(config_data)), tmp_path)
    seen: list[tuple[str, str, int, object]] = []
    both_cameras, zoomed = asyncio.Event(), asyncio.Event()

    async def take(emission: LiveSourceEmission) -> None:
        camera, layer, frame, position = emission
        seen.append((camera, layer.value, live_source_header(frame).frame_idx, position))
        if {entry[0] for entry in seen} == {"camera", "camera_2"}:
            both_cameras.set()
        if layer.value == "viewport":
            zoomed.set()

    microscope.live.subscribe(take)
    await microscope.open()
    try:
        await microscope.set_preview_channels(["camera", "camera_2"])
        revision = microscope.view.value.live.stream_revision
        await microscope.start_preview()
        async with asyncio.timeout(5):
            await both_cameras.wait()
        await microscope.stop_preview()
        assert microscope.view.value.live.stream_revision == revision + 1
        assert all(position is not None for *_, position in seen)

        last = max((entry for entry in seen if entry[0] == "camera"), key=lambda entry: entry[2])
        seen.clear()
        microscope._hal.area_cameras["camera"].live_viewport.update(LiveViewport(x=0.25, y=0.25, w=0.5, h=0.5))
        async with asyncio.timeout(5):
            await zoomed.wait()
        assert seen[-1] == ("camera", "viewport", last[2], last[3])  # a zoom of the stopped image keeps its place

        seen.clear()
        await microscope.select_profile("rfp")
        assert microscope.view.value.live.stream_revision == revision + 2
        microscope._hal.area_cameras["camera"].live_viewport.update(LiveViewport(x=0.0, y=0.0, w=0.5, h=0.5))
        await asyncio.sleep(0.3)
        assert seen == []  # the old stream ended with the profile change
    finally:
        await microscope.close()


async def test_the_planes_follow_a_hand_moved_objective_and_a_zoom_keeps_its_box(
    config_data: dict[str, Any], tmp_path: Path
) -> None:
    microscope = _microscope(objective_turret(simulated(config_data)), tmp_path)
    zoomed: list[int] = []
    new_zoom = asyncio.Event()

    async def take(emission: LiveSourceEmission) -> None:
        _, layer, frame, _ = emission
        if layer.value == "viewport":
            zoomed.append(live_source_header(frame).source_rect_px.width)
            new_zoom.set()

    def width() -> float:
        (plane,) = microscope.view.value.live.planes
        return plane.pictures["camera"].height[0]  # the camera is turned: its height runs along the plane's right

    microscope.live.subscribe(take)
    await microscope.open()
    try:
        assert width() == pytest.approx(-2662.4)  # 2048 px of 6.5 µm behind 5x
        await microscope.start_preview()
        await microscope.update_viewport(["camera"], (-250.0, -250.0, 500.0, 500.0))
        async with asyncio.timeout(5):
            await new_zoom.wait()
        at_5x, revision = zoomed[-1], microscope.view.value.live.stream_revision

        new_zoom.clear()
        await microscope.execute_device_command("turret", "move_to", ["high"])
        async with asyncio.timeout(5):
            while width() != pytest.approx(-1331.2):
                await new_zoom.wait()
                new_zoom.clear()
        assert microscope.view.value.live.stream_revision > revision
        async with asyncio.timeout(5):
            await new_zoom.wait()
        assert zoomed[-1] == pytest.approx(2 * at_5x, rel=0.1)  # the same box covers twice the sensor at 10x

        with pytest.raises(RejectedError, match="1 plane"):
            await microscope.update_viewport(["laser"], None)
    finally:
        await microscope.close()
