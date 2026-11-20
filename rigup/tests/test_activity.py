import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from enum import Enum

import pytest
from rigup.activity import Activity, ActivityBusyError, ActivityInfo, ActivityScheduler


class Word(Enum):
    PROFILE = "profile"
    STATE = "state"


class _Bench:
    """A small instrument: device operations, a profile that a preview follows, and the log of what ran."""

    def __init__(self) -> None:
        self.scheduler = ActivityScheduler(covers={"tiger": {"x_axis", "y_axis", "z_axis"}})
        self.log: list[str] = []
        self.preview: Activity | None = None

    async def set_props(self, device_id: str) -> None:
        async with self.scheduler.run("set properties", requires={device_id}):
            self.log.append(f"set {device_id}")

    async def apply_profile(self, *, fail: bool = False) -> None:
        async with self.scheduler.run("apply a profile", requires={Word.PROFILE}):
            await self.set_props("laser")
            if fail:
                raise RuntimeError("bad profile")
            self.log.append("profile applied")

    async def start_preview(self) -> None:
        async with self.scheduler.run("start the preview", requires=()):
            self.preview = await self.scheduler.start(
                ActivityInfo(kind="preview"), {Word.PROFILE}, stop=self._stop, restart=self._restart
            )
            self.log.append("preview on")

    async def _stop(self) -> None:
        self.log.append("preview stopped")

    @asynccontextmanager
    async def _restart(self) -> AsyncGenerator[None]:
        assert self.preview is not None
        await self.preview.end()
        self.log.append("preview off")
        yield
        await self.start_preview()

    async def start(self, kind: str, requires: set[object]) -> Activity:
        async with self.scheduler.run(f"start {kind}", requires=()):
            return await self.scheduler.start(ActivityInfo(kind=kind), requires, stop=_nothing)


async def _nothing() -> None:
    pass


@pytest.fixture
def bench() -> _Bench:
    return _Bench()


async def test_operations_run_1_at_a_time(bench: _Bench) -> None:
    async def slow(device_id: str) -> None:
        async with bench.scheduler.run("slow", requires={device_id}):
            bench.log.append(f"{device_id} start")
            await asyncio.sleep(0.01)
            bench.log.append(f"{device_id} end")

    await asyncio.gather(slow("camera"), slow("laser"))

    assert bench.log == ["camera start", "camera end", "laser start", "laser end"]


async def test_an_operation_inside_an_operation_does_not_wait(bench: _Bench) -> None:
    await asyncio.wait_for(bench.apply_profile(), timeout=1)

    assert bench.log == ["set laser", "profile applied"]


async def test_an_operation_that_requires_nothing_of_a_preview_runs_live(bench: _Bench) -> None:
    await bench.start_preview()
    bench.log.clear()

    await bench.set_props("laser")

    assert bench.log == ["set laser"]


async def test_an_operation_that_requires_what_a_preview_requires_restarts_it(bench: _Bench) -> None:
    await bench.start_preview()
    bench.log.clear()

    await bench.apply_profile()

    assert bench.log == ["preview off", "set laser", "profile applied", "preview on"]
    assert bench.scheduler.activities.value == (ActivityInfo(kind="preview"),)


async def test_a_failed_operation_ends_the_preview_and_starts_no_new_one(bench: _Bench) -> None:
    await bench.start_preview()
    bench.log.clear()

    with pytest.raises(RuntimeError, match="bad profile"):
        await bench.apply_profile(fail=True)

    assert bench.log == ["preview off", "set laser"]
    assert bench.scheduler.activities.value == ()


async def test_2_activities_never_require_the_same_resource(bench: _Bench) -> None:
    await bench.start_preview()

    with pytest.raises(ActivityBusyError, match="Unable to start capture while preview is running"):
        await bench.start("capture", {"camera", Word.PROFILE})


async def test_an_activity_that_cannot_restart_refuses_an_operation(bench: _Bench) -> None:
    await bench.start("capture", {"camera", "laser", Word.PROFILE, Word.STATE})

    with pytest.raises(ActivityBusyError, match="Unable to set properties while capture is running"):
        await bench.set_props("camera")
    assert bench.log == []


async def test_a_hub_stands_for_the_devices_it_covers(bench: _Bench) -> None:
    await bench.start("calibration", {"z_axis"})

    with pytest.raises(ActivityBusyError, match="while calibration is running"):
        await bench.set_props("tiger")
    await bench.set_props("x_axis")

    assert bench.log == ["set x_axis"]


async def test_requiring_a_hub_requires_the_devices_it_covers(bench: _Bench) -> None:
    await bench.start("homing", {"tiger"})

    with pytest.raises(ActivityBusyError, match="while homing is running"):
        await bench.set_props("y_axis")
    await bench.set_props("camera")

    assert bench.log == ["set camera"]


async def test_a_task_made_in_an_operation_takes_the_lock_again_after_it(bench: _Bench) -> None:
    async def later() -> None:
        await asyncio.sleep(0.01)
        await bench.set_props("camera")

    async with bench.scheduler.run("spawn", requires=()):
        job = asyncio.create_task(later())
    async with bench.scheduler.run("hold the lock", requires=()):
        bench.log.append("holder in")
        await asyncio.sleep(0.03)
        bench.log.append("holder out")
    await job

    assert bench.log == ["holder in", "holder out", "set camera"]


async def test_activities_show_what_runs_until_each_one_ends(bench: _Bench) -> None:
    capture = await bench.start("capture", {"camera"})
    await capture.update(ActivityInfo(kind="capture 2 of 5"))
    assert bench.scheduler.activities.value == (ActivityInfo(kind="capture 2 of 5"),)

    await capture.end()
    await capture.end()
    assert bench.scheduler.activities.value == ()
    await bench.set_props("camera")


async def test_a_scheduler_with_no_covers_keeps_each_resource_apart() -> None:
    scheduler = ActivityScheduler()
    await scheduler.start(ActivityInfo(kind="capture"), {"camera"}, stop=_nothing)

    async with scheduler.run("move the stage", requires={"x_axis"}):
        pass
    with pytest.raises(ActivityBusyError, match="Unable to set a region while capture is running"):
        async with scheduler.run("set a region", requires={"camera"}):
            pass


async def test_stop_all_stops_and_ends_every_activity_even_when_one_fails(bench: _Bench) -> None:
    await bench.start_preview()

    async def fail() -> None:
        raise RuntimeError("stuck")

    async with bench.scheduler.run("start a capture", requires=()):
        await bench.scheduler.start(ActivityInfo(kind="capture"), {"camera"}, stop=fail)

    with pytest.raises(ExceptionGroup, match="Not every activity stopped cleanly"):
        await bench.scheduler.stop_all()
    assert "preview stopped" in bench.log
    assert bench.scheduler.activities.value == ()


async def test_an_operation_that_does_not_restart_leaves_a_restartable_activity_and_is_refused_by_others(
    bench: _Bench,
) -> None:
    await bench.start_preview()
    async with bench.scheduler.run("tune the profile", requires={Word.PROFILE}, restart=False):
        pass
    assert "preview off" not in bench.log

    await bench.start("capture", {"camera"})
    with pytest.raises(ActivityBusyError, match="Unable to set a region while capture is running"):
        async with bench.scheduler.run("set a region", requires={"camera"}, restart=False):
            pass
