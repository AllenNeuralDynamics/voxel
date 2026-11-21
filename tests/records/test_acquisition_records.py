import asyncio
import datetime
import json
import logging
import uuid
from pathlib import Path, PurePosixPath

import pytest
from vxlib.imaging.writer import FrameRange
from vxlib.issues import Failure
from vxlib.vector import Transform, Vec3D

from vxl.records import (
    ACQUISITION_FILE,
    LOG_FILE,
    Acquisition,
    CaptureError,
    Image,
    Records,
    Visit,
    VisitRecording,
)
from vxl.storage import LocalLocation, LocationRole, LocationStatus, StorageSpec

_TRANSFORM = Transform(
    Vec3D(z=0.0, y=0.0, x=0.0),
    (Vec3D(z=2.0, y=0.0, x=0.0), Vec3D(z=0.0, y=0.5, x=0.0), Vec3D(z=0.0, y=0.0, x=0.5)),
    (10, 64, 64),
)
_LOCATION = LocalLocation(
    role=LocationRole.DESTINATION, status=LocationStatus.WRITING, host="rig", path="/data/runs/1/camera.ome.zarr"
)


def _acquisition(visits: int = 1) -> Acquisition:
    visit = Visit(task="brain", profile="gfp", channels={"gfp": {"camera": Image(transform=_TRANSFORM)}})
    return Acquisition(
        id=uuid.uuid4(),
        operator="ana",
        host="rig",
        created_at=datetime.datetime.now(tz=datetime.UTC),
        storage=StorageSpec(path=PurePosixPath("runs/1")),
        instrument_config={"id": "exaspim-1"},
        instrument_state={"plan": [{"id": "brain", "metadata": {"notes": "left hemisphere"}}]},
        visits=[visit] * visits,
    )


async def _capture(visit: VisitRecording, frames: int) -> None:
    await visit.images_opened({"camera": _LOCATION})
    await visit.frames("camera", frames)


async def _fail(error: BaseException) -> None:
    raise error


@pytest.fixture
def records(tmp_path: Path) -> Records:
    return Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / "data" / spec.path)


def _file(tmp_path: Path, name: str = ACQUISITION_FILE) -> str:
    return (tmp_path / "data" / "runs/1" / name).read_text(encoding="utf-8")


async def test_an_acquisition_records_each_visit_and_its_file_adds_the_statuses(
    records: Records, tmp_path: Path
) -> None:
    acquisition = _acquisition(3)

    async def run_all() -> None:
        async with records.record(acquisition) as run:
            for index in range(3):
                async with run.visit(index) as visit:
                    await _capture(visit, 10 if index == 0 else 4)

    with pytest.raises(CaptureError):
        await run_all()

    stored = await records.acquisitions.get(acquisition.id)
    assert stored.status == "failed"
    assert [visit.status for visit in stored.visits] == ["completed", "failed", "skipped"]
    assert [visit.image_status("camera") for visit in stored.visits] == ["completed", "partial", "skipped"]
    assert [failure.code for failure in stored.failures] == ["acquisition.frames_missing"]
    assert Acquisition.model_validate_json(stored.model_dump_json(by_alias=True)) == stored

    written = json.loads(_file(tmp_path))
    assert (written["schema"], written["revision"], written["status"]) == (
        "voxel.acquisition/1",
        stored.revision,
        "failed",
    )
    assert written["visits"][1]["channels"]["gfp"]["camera"]["status"] == "partial"


async def test_capture_and_cleanup_errors_are_both_kept(records: Records) -> None:
    acquisition = _acquisition()
    group = ExceptionGroup("visit 0", [TimeoutError("grab timed out"), RuntimeError("stack did not close")])
    with pytest.raises(ExceptionGroup):
        async with records.record(acquisition) as run, run.visit(0):
            await _fail(group)
    stored = await records.acquisitions.get(acquisition.id)
    assert [failure.msg for failure in stored.visits[0].failures] == [
        "TimeoutError: grab timed out",
        "RuntimeError: stack did not close",
    ]


async def test_a_failure_before_the_stacks_open_fails_the_visit(records: Records) -> None:
    acquisition = _acquisition()
    stage = Failure(code="acquisition.stage", msg="the stage did not stop", loc=("x_axis",))
    with pytest.raises(CaptureError):
        async with records.record(acquisition) as run, run.visit(0):
            await _fail(CaptureError(stage))
    stored = await records.acquisitions.get(acquisition.id)
    assert (stored.visits[0].status, stored.visits[0].image_status("camera")) == ("failed", "failed")
    assert stored.visits[0].failures == [stage]


async def test_a_cancel_cancels_and_a_second_cancel_does_not_stop_the_ending_save(records: Records) -> None:
    acquisition = _acquisition(2)

    async def body() -> None:
        async with records.record(acquisition) as run, run.visit(0):
            await asyncio.sleep(10)

    task = asyncio.create_task(body())
    for _ in range(2):
        await asyncio.sleep(0.05)
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0.1)
    stored = await records.acquisitions.get(acquisition.id)
    assert stored.status == "cancelled"
    assert [visit.status for visit in stored.visits] == ["cancelled", "skipped"]


async def test_a_failed_ending_save_keeps_the_real_error_and_the_next_start_interrupts(
    records: Records, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquisition = _acquisition()
    save = records.acquisitions.save

    async def full_disk(value: Acquisition, *, write_file: bool = True) -> bool:
        if value.result is not None:
            raise OSError("disk full")
        return await save(value, write_file=write_file)

    monkeypatch.setattr(records.acquisitions, "save", full_disk)
    with pytest.raises(TimeoutError, match="the real error"):
        async with records.record(acquisition):
            await _fail(TimeoutError("the real error"))
    monkeypatch.undo()

    assert await records.acquisitions.interrupt_open() == [acquisition.id]
    stored = await records.acquisitions.get(acquisition.id)
    assert (stored.status, stored.visits[0].status) == ("interrupted", "skipped")
    assert [failure.code for failure in stored.failures] == ["acquisition.interrupted"]


async def test_the_run_cannot_change_after_its_block(records: Records) -> None:
    async with records.record(_acquisition()) as run, run.visit(0) as visit:
        await _capture(visit, 10)
    with pytest.raises(RuntimeError, match="has ended"):
        async with run.visit(0):
            pass


async def test_progress_is_saved_without_a_file_write_and_an_older_snapshot_is_ignored(
    records: Records, tmp_path: Path
) -> None:
    acquisition = _acquisition()
    seen: list[int] = []
    records.acquisitions.subscribe(lambda value: seen.append(value.revision))
    async with records.record(acquisition) as run, run.visit(0) as visit:
        await visit.images_opened({"camera": _LOCATION})
        file_revision = json.loads(_file(tmp_path))["revision"]
        await visit.frames("camera", 5)
        assert json.loads(_file(tmp_path))["revision"] == file_revision  # saved, but no file write
        assert (await records.acquisitions.get(acquisition.id)).visits[0].progress == (5, 10)
        await visit.frames("camera", 10)
        older = run.value.model_copy(update={"revision": 2})
    assert seen == sorted(seen)
    assert not await records.acquisitions.save(older)


async def test_a_file_that_cannot_be_written_does_not_stop_the_acquisition(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where a folder should be", encoding="utf-8")
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: blocked / spec.path)
    acquisition = _acquisition()
    async with records.record(acquisition) as run, run.visit(0) as visit:
        await _capture(visit, 10)
    assert (await records.acquisitions.get(acquisition.id)).status == "completed"
    assert "could not be written" in caplog.text


async def test_the_log_window_follows_the_acquisition_and_its_end_writes_its_log(
    records: Records, tmp_path: Path
) -> None:
    log = logging.getLogger("vxl.test_records")
    log.setLevel(logging.INFO)
    acquisition = _acquisition()
    async with records.logs.capture():
        log.info("before")
        async with records.record(acquisition) as run, run.visit(0) as visit:
            log.info("during")
            await _capture(visit, 10)
        log.info("after")
    messages = [json.loads(line)["message"] for line in _file(tmp_path, LOG_FILE).splitlines()]
    assert "during" in messages
    assert "before" not in messages
    assert "after" not in messages


async def test_dropped_frames_leave_gaps_and_only_unaccounted_frames_fail_a_visit(records: Records) -> None:
    acquisition = _acquisition(2)

    async def run_all() -> None:
        async with records.record(acquisition) as run:
            async with run.visit(0) as visit:
                await _capture(visit, 6)
                await visit.frames_dropped("camera", [FrameRange(first=6, last=9)])
            async with run.visit(1) as visit:
                await _capture(visit, 6)
                await visit.frames_dropped("camera", [FrameRange(first=6, last=7)])

    with pytest.raises(CaptureError):
        await run_all()

    stored = await records.acquisitions.get(acquisition.id)
    assert [visit.status for visit in stored.visits] == ["completed", "failed"]
    assert [visit.image_status("camera") for visit in stored.visits] == ["gaps", "partial"]
    assert stored.visits[1].missing() == {"camera": 2}
