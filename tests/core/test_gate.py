import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from enum import Enum

import pytest

from vxl.core.errors import BusyError
from vxl.core.instrument.gate import Activity, Gate, Hold


class Word(Enum):
    PROFILE = "profile"
    STATE = "state"


class _Bench:
    """A small instrument: device commands, a profile that a preview follows, and the log of what ran."""

    def __init__(self) -> None:
        self.gate = Gate(covers={"tiger": {"x_axis", "y_axis", "z_axis"}})
        self.log: list[str] = []
        self.preview: Hold | None = None

    async def set_props(self, uid: str) -> None:
        async with self.gate.command("set properties", touches={uid}):
            self.log.append(f"set {uid}")

    async def apply_profile(self, *, fail: bool = False) -> None:
        async with self.gate.command("apply a profile", touches={Word.PROFILE}):
            await self.set_props("laser")
            if fail:
                raise RuntimeError("bad profile")
            self.log.append("profile applied")

    async def start_preview(self) -> None:
        async with self.gate.command("start the preview", touches=()):
            self.preview = await self.gate.begin(Activity(kind="preview"), {Word.PROFILE}, restart=self._restart)
            self.log.append("preview on")

    @asynccontextmanager
    async def _restart(self) -> AsyncGenerator[None]:
        assert self.preview is not None
        await self.gate.end(self.preview)
        self.log.append("preview off")
        yield
        await self.start_preview()

    async def begin(self, kind: str, holds: set[object]) -> Hold:
        async with self.gate.command(f"start {kind}", touches=()):
            return await self.gate.begin(Activity(kind=kind), holds)


@pytest.fixture
def bench() -> _Bench:
    return _Bench()


async def test_commands_run_1_at_a_time(bench: _Bench) -> None:
    async def slow(uid: str) -> None:
        async with bench.gate.command("slow", touches={uid}):
            bench.log.append(f"{uid} start")
            await asyncio.sleep(0.01)
            bench.log.append(f"{uid} end")

    await asyncio.gather(slow("camera"), slow("laser"))

    assert bench.log == ["camera start", "camera end", "laser start", "laser end"]


async def test_a_command_inside_a_command_passes(bench: _Bench) -> None:
    await asyncio.wait_for(bench.apply_profile(), timeout=1)

    assert bench.log == ["set laser", "profile applied"]


async def test_a_preview_lets_a_device_command_run_live(bench: _Bench) -> None:
    await bench.start_preview()
    bench.log.clear()

    await bench.set_props("laser")

    assert bench.log == ["set laser"]


async def test_a_command_on_a_held_resource_restarts_the_preview(bench: _Bench) -> None:
    await bench.start_preview()
    bench.log.clear()

    await bench.apply_profile()

    assert bench.log == ["preview off", "set laser", "profile applied", "preview on"]
    assert bench.gate.activities.value == (Activity(kind="preview"),)


async def test_a_failed_command_ends_the_preview_and_starts_no_new_one(bench: _Bench) -> None:
    await bench.start_preview()
    bench.log.clear()

    with pytest.raises(RuntimeError, match="bad profile"):
        await bench.apply_profile(fail=True)

    assert bench.log == ["preview off", "set laser"]
    assert bench.gate.activities.value == ()


async def test_2_activities_never_hold_the_same_resource(bench: _Bench) -> None:
    await bench.start_preview()

    with pytest.raises(BusyError, match="Unable to start capture while preview is running"):
        await bench.begin("capture", {"camera", Word.PROFILE})


async def test_an_activity_that_cannot_restart_refuses_a_command(bench: _Bench) -> None:
    await bench.begin("capture", {"camera", "laser", Word.PROFILE, Word.STATE})

    with pytest.raises(BusyError, match="Unable to set properties while capture is running"):
        await bench.set_props("camera")
    assert bench.log == []


async def test_the_job_of_an_activity_passes_its_own_holds(bench: _Bench) -> None:
    capture = await bench.begin("capture", {"camera"})

    with bench.gate.inside(capture):
        job = asyncio.create_task(bench.set_props("camera"))
    await job

    assert bench.log == ["set camera"]


async def test_a_hub_stands_for_the_devices_it_covers(bench: _Bench) -> None:
    await bench.begin("calibration", {"z_axis"})

    with pytest.raises(BusyError, match="while calibration is running"):
        await bench.set_props("tiger")
    await bench.set_props("x_axis")

    assert bench.log == ["set x_axis"]


async def test_holding_a_hub_holds_the_devices_it_covers(bench: _Bench) -> None:
    await bench.begin("homing", {"tiger"})

    with pytest.raises(BusyError, match="while homing is running"):
        await bench.set_props("y_axis")
    await bench.set_props("camera")

    assert bench.log == ["set camera"]


async def test_a_task_made_in_a_command_takes_the_lock_again_after_it(bench: _Bench) -> None:
    async def later() -> None:
        await asyncio.sleep(0.01)
        await bench.set_props("camera")

    async with bench.gate.command("spawn", touches=()):
        job = asyncio.create_task(later())
    async with bench.gate.command("hold the lock", touches=()):
        bench.log.append("holder in")
        await asyncio.sleep(0.03)
        bench.log.append("holder out")
    await job

    assert bench.log == ["holder in", "holder out", "set camera"]


async def test_activities_show_what_runs(bench: _Bench) -> None:
    capture = await bench.begin("capture", {"camera"})
    await bench.gate.update(capture, Activity(kind="capture 2 of 5"))
    assert bench.gate.activities.value == (Activity(kind="capture 2 of 5"),)

    await bench.gate.end(capture)
    assert bench.gate.activities.value == ()
