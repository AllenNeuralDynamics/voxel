"""The light of a lab microscope, through the commands an app would call."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from vxl.core.errors import RejectedError

from .demo import Session
from .instrument import LabMicroscope


@pytest.fixture
async def microscope(tmp_path: Path) -> AsyncIterator[LabMicroscope]:
    session = Session(tmp_path)
    await session.microscope.open()
    yield session.microscope
    await session.microscope.close()


async def _light(microscope: LabMicroscope) -> tuple[bool, float, bool, float]:
    """The laser's state and power, and the AOM line's state and transmission."""
    laser = (await microscope.get_device_properties("laser", ["is_enabled", "power_mw"])).results
    aom = (await microscope.get_device_properties("aom", ["enabled_lines", "transmissions"])).results
    value: Any = {name: result.unwrap().value for name, result in {**laser, **aom}.items()}
    return value["is_enabled"], value["power_mw"], "561" in value["enabled_lines"], value["transmissions"]["561"]


async def test_the_preview_shows_dim_or_full_and_switches_without_a_restart(microscope: LabMicroscope) -> None:
    await microscope.set_channel_power("camera", 10)
    await microscope.set_channel_dim_power("camera", 1)
    await microscope.start_preview()
    assert await _light(microscope) == (True, 100, True, pytest.approx(0.01))
    hold = microscope._running
    await microscope.set_preview_light("full")
    assert await _light(microscope) == (True, 100, True, pytest.approx(0.1))
    assert microscope._running is hold


async def test_a_power_out_of_reach_is_refused_and_changes_nothing(microscope: LabMicroscope) -> None:
    await microscope.set_preview_light("full")
    await microscope.set_channel_power("camera", 12)
    await microscope.start_preview()
    with pytest.raises(RejectedError, match=r"gives 0.5..100 mW, not 500 mW"):
        await microscope.set_channel_power("camera", 500)
    assert microscope.channel_powers()["camera"] == (12, None)
    assert await _light(microscope) == (True, 100, True, pytest.approx(0.12))


async def test_each_profile_keeps_its_powers(microscope: LabMicroscope) -> None:
    await microscope.set_preview_light("full")
    await microscope.set_channel_power("camera", 12)
    await microscope.start_preview()
    await microscope.select_profile("rfp")
    await microscope.set_channel_power("camera", 3)
    await microscope.select_profile("gfp")
    assert await _light(microscope) == (True, 100, True, pytest.approx(0.12))


async def test_stopping_closes_the_line_and_keeps_the_head_warm(microscope: LabMicroscope) -> None:
    await microscope.start_preview()
    await microscope.stop_preview()
    enabled, _, line_open, _ = await _light(microscope)
    assert (enabled, line_open) == (True, False)
