"""The light of a lab microscope, through the commands an app would call."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from vxl.core.errors import RejectedError

from .demo import Session
from .instrument import LabMicroscope


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[Session]:
    session = Session(tmp_path)
    await session.microscope.open()
    yield session
    await session.microscope.close()


async def _light(session: Session) -> dict[str, Any]:
    """Whether the laser and the AOTF line are on, the line's power and what drives it, and whether the shutter is
    open."""
    laser = await session.props("laser", "is_on", "control_mode")
    aotf = await session.props("aotf", "is_on", "power", "control_mode")
    shutter = await session.props("shutter", "is_open")
    return {
        "on": (laser["is_on"], aotf["is_on"], shutter["is_open"]),
        "power": aotf["power"],
        "controls": (laser["control_mode"], aotf["control_mode"]),
    }


def _saved(microscope: LabMicroscope, profile: str = "gfp") -> dict[str, Any]:
    return microscope.state.value.profiles[profile].model_dump(mode="json")["power"]


async def test_a_preview_lights_the_dim_power_and_switches_to_full_without_a_restart(session: Session) -> None:
    m = session.microscope
    assert (await _light(session))["on"] == (False, False, False)
    await m.start_preview()
    assert await _light(session) == {"on": (True, True, True), "power": 3, "controls": ("software", "digital")}
    running = m._preview
    await m.set_power_mode("full")
    assert (await _light(session))["power"] == 30
    assert m._preview is running
    await m.stop_preview()
    assert (await _light(session))["on"] == (True, False, False)


async def test_a_power_is_saved_for_the_side_the_light_goes_now(session: Session) -> None:
    m = session.microscope
    await m.set_power_mode("full")
    await m.set_power("aotf", 35)
    await m.set_position_rule("flip", "right")
    await m.apply_profile()
    assert (await _light(session))["power"] == 42
    await m.set_dim_power("aotf", 5)
    assert _saved(m) == {
        "full": {"laser": "50 mW", "aotf": {"flip": {"left": "35 %", "right": "42 %"}}},
        "dim": {"aotf": {"flip": {"left": "3 %", "right": "5 %"}}},
    }


async def test_a_power_out_of_range_is_refused_and_nothing_changes(session: Session) -> None:
    m = session.microscope
    await m.set_power_mode("full")
    before = _saved(m)
    with pytest.raises(RejectedError, match=r"cannot do 500 % \(it can do 0.5..100 %\)"):
        await m.set_power("aotf", 500)
    assert _saved(m) == before
    assert (await _light(session))["power"] == 30


async def test_the_timelines_of_a_profile_say_what_drives_each_device(session: Session) -> None:
    m = session.microscope
    assert (await _light(session))["controls"] == ("software", "digital")
    await m.select_profile("align")
    assert (await _light(session))["controls"] == ("software", "software")
    await m.select_profile("analog")
    assert (await _light(session))["controls"] == ("analog", "digital")
    with pytest.raises(RejectedError, match="A wire sets the power of 'laser'"):
        await m.set_power("laser", 20)


async def test_lights_off_keeps_a_stopped_laser_on_and_lasers_off_turns_it_off(session: Session) -> None:
    m = session.microscope
    await m.start_preview()
    await m.lights_off()
    assert (await _light(session))["on"] == (True, False, False)
    assert [activity.kind for activity in m.activities.value] == ["preview"]
    await m.lasers_off()
    assert (await _light(session))["on"] == (False, False, False)


async def test_a_laser_that_nothing_stops_turns_off_when_it_is_not_asked_for(session: Session) -> None:
    m = session.microscope
    await m.execute_device_command("laser_561", "on")
    assert (await session.props("laser_561", "is_on"))["is_on"] is True
    await m.start_preview()
    assert (await session.props("laser_561", "is_on"))["is_on"] is False


async def test_a_preview_runs_dark_while_the_light_is_blocked_and_lights_again_after(session: Session) -> None:
    m = session.microscope
    await m.start_preview()
    await m.set_position_rule("flip", "closed")
    await m.apply_profile()
    assert (await _light(session))["on"] == (True, False, False)
    assert [activity.kind for activity in m.activities.value] == ["preview"]
    await m.set_position_rule("flip", "left")
    await m.apply_profile()
    assert (await _light(session))["on"] == (True, True, True)
