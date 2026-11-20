"""The light of the SPIM preview: dim and full power, lights and lasers off during a preview, and a preview that
runs dark. How every instrument sets its light is tested in ``tests/station/test_light.py``."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from vxl_instruments.spim.instrument import Microscope

from vxl.records import Records
from vxl.station.instrument.folder import InstrumentFolder
from vxl.system import System

from .support import simulated, template

_DIGITAL = {"kind": "digital", "off": "0 V", "on": "5 V"}
_LIGHT = "vxl.devices.light.simulated"
_FLIP = {
    "target": "vxl.devices.axes.discrete.mapped.OwnedMappedDiscreteAxis",
    "init": {
        "axis": {
            "target": "vxl.devices.axes.simulated.SimulatedContinuousAxis",
            "init": {"lower_limit": 0, "upper_limit": 100},
        },
        "slots": {
            "0": {"label": "left", "position": 0},
            "1": {"label": "right", "position": 10},
            "2": {"label": "closed", "position": 20},
        },
        "tolerance": 1,
    },
}


@pytest.fixture
async def microscope(config_data: dict[str, Any], tmp_path: Path) -> AsyncIterator[Microscope]:
    """An open microscope with a 488 nm laser, 1 AOTF line, a shutter, and a flip mirror that sends the light to the
    left or the right arm, or nowhere when it is ``closed``. A 561 nm laser has nothing after it to stop its light.
    The generator gates the AOTF line.

    Profile ``gfp`` gates the AOTF line with the generator, and gives it 1 power for each side."""
    data = simulated(config_data)
    data["devices"] |= {
        "laser": {"target": f"{_LIGHT}.SimulatedLaser", "init": {"wavelength": 488}},
        "laser_561": {"target": f"{_LIGHT}.SimulatedLaser", "init": {"wavelength": 561}},
        "aotf": {"target": f"{_LIGHT}.SimulatedModulator", "init": {"pins": ["ttl_in"]}},
        "shutter": {"target": f"{_LIGHT}.SimulatedShutter"},
        "flip": _FLIP,
    }
    data["parts"] |= {"left_arm": {"kind": "mirror"}, "right_arm": {"kind": "mirror"}}
    data["optics"] |= {
        "laser": {"to": "aotf"},
        "laser_561": {"to": "flip"},
        "aotf": {"to": "shutter"},
        "shutter": {"to": "flip"},
        "flip": {"to": {"left": "left_arm", "right": "right_arm"}},
        "left_arm": {"to": "galvo"},
        "right_arm": {"to": "galvo"},
    }
    wires = data["wiring"]["ao_main"]
    del wires["laser"]
    wires["gate"] = {"pin": "ao1", "to": ["aotf/ttl_in"], **_DIGITAL}
    default = data["default"]
    default["positions"] = {"flip": "left"}
    gfp = default["profiles"]["gfp"]
    signals = gfp["timelines"]["ao_main"]["signals"]
    signals["gate"] = signals.pop("laser")
    gfp["power"] = {
        "laser": {"full": "50 mW"},
        "aotf": {"router": "flip", "full": {"left": "30 %", "right": "42 %"}, "dim": {"left": "3 %", "right": "4 %"}},
    }

    folder = InstrumentFolder.create(template(data), "left", tmp_path)
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    microscope = Microscope(folder, records=records, system=system)
    await microscope.open()
    yield microscope
    await microscope.close()


async def _props(microscope: Microscope, device: str, *names: str) -> dict[str, Any]:
    results = await microscope.get_device_properties(device, names)
    return {name: results.results[name].unwrap().value for name in names}


async def _light(microscope: Microscope) -> dict[str, Any]:
    """Whether the laser and the AOTF line are on, the line's power and what controls each, and whether the shutter
    is open."""
    laser = await _props(microscope, "laser", "is_on", "control_mode")
    aotf = await _props(microscope, "aotf", "is_on", "power", "control_mode")
    shutter = await _props(microscope, "shutter", "is_open")
    return {
        "on": (laser["is_on"], aotf["is_on"], shutter["is_open"]),
        "power": aotf["power"],
        "controls": (laser["control_mode"], aotf["control_mode"]),
    }


async def test_a_preview_lights_the_dim_power_and_switches_to_full_without_a_restart(microscope: Microscope) -> None:
    assert (await _light(microscope))["on"] == (False, False, False)
    await microscope.start_preview()
    assert await _light(microscope) == {"on": (True, True, True), "power": 3, "controls": ("software", "digital")}
    running = microscope._preview
    await microscope.set_power_mode("full")
    assert (await _light(microscope))["power"] == 30
    assert microscope._preview is running
    await microscope.stop_preview()
    assert (await _light(microscope))["on"] == (True, False, False)


async def test_lights_off_keeps_a_stopped_laser_on_and_lasers_off_turns_it_off(microscope: Microscope) -> None:
    await microscope.start_preview()
    await microscope.lights_off()
    assert (await _light(microscope))["on"] == (True, False, False)
    assert [activity.kind for activity in microscope.view.value.activities] == ["preview"]
    await microscope.lasers_off()
    assert (await _light(microscope))["on"] == (False, False, False)


async def test_a_laser_that_nothing_stops_turns_off_when_it_is_not_asked_for(microscope: Microscope) -> None:
    await microscope.execute_device_command("laser_561", "on")
    assert (await _props(microscope, "laser_561", "is_on"))["is_on"] is True
    await microscope.start_preview()
    assert (await _props(microscope, "laser_561", "is_on"))["is_on"] is False


async def test_a_preview_runs_dark_while_the_light_is_blocked_and_lights_again_after(microscope: Microscope) -> None:
    await microscope.start_preview()
    await microscope.set_position_rule("flip", "closed")
    await microscope.apply_profile()
    assert (await _light(microscope))["on"] == (True, False, False)
    assert [activity.kind for activity in microscope.view.value.activities] == ["preview"]
    await microscope.set_position_rule("flip", "left")
    await microscope.apply_profile()
    assert (await _light(microscope))["on"] == (True, True, True)
