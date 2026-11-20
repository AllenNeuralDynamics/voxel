"""How every instrument sets its light: powers for each side of a router, out-of-range powers, and what controls each
device. The preview's light is tested with the SPIM microscope."""

import copy
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from vxl.station.errors import RejectedError
from vxl.station.instrument.basic import BasicInstrument

from .support import basic, rig, simulated

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
async def instrument(tmp_path: Path) -> AsyncIterator[BasicInstrument]:
    """An open instrument with a 488 nm laser, 1 AOTF line, a shutter, and a flip mirror that sends the light to the
    left or the right arm, or nowhere when it is ``closed``. A 561 nm laser has nothing after it to stop its light.
    The generator can gate the AOTF line and set the 488 nm laser's power.

    Profile ``gfp`` gates the AOTF line with the generator, and gives it 1 power for each side. ``align`` is the same
    with no gate signal. ``analog`` also sets the laser's power with a wire."""
    data = simulated(rig())
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
    wires["laser_power"] = {
        "pin": "ao4",
        "to": ["laser/analog_in"],
        "kind": "analog",
        "limits": {"V": [0, 5]},
        "park": "0 V",
    }
    default = data["default"]
    default["positions"] = {"flip": "left"}
    gfp = default["profiles"]["gfp"]
    signals = gfp["timelines"]["ao_main"]["signals"]
    signals["gate"] = signals.pop("laser")
    gfp["power"] = {
        "laser": {"full": "50 mW"},
        "aotf": {"router": "flip", "full": {"left": "30 %", "right": "42 %"}, "dim": {"left": "3 %", "right": "4 %"}},
    }
    align = copy.deepcopy(gfp)
    del align["timelines"]["ao_main"]["signals"]["gate"]
    analog = copy.deepcopy(gfp)
    analog["timelines"]["ao_main"]["signals"]["laser_power"] = {"kind": "constant", "value": "2 V"}
    del analog["power"]["laser"]
    default["profiles"] |= {"align": align, "analog": analog}

    instrument = basic(data, tmp_path)
    await instrument.open()
    yield instrument
    await instrument.close()


async def _props(instrument: BasicInstrument, device: str, *names: str) -> dict[str, Any]:
    results = await instrument.get_device_properties(device, names)
    return {name: results.results[name].unwrap().value for name in names}


async def _light(instrument: BasicInstrument) -> dict[str, Any]:
    """Whether the laser and the AOTF line are on, the line's power and what controls each, and whether the shutter
    is open."""
    laser = await _props(instrument, "laser", "is_on", "control_mode")
    aotf = await _props(instrument, "aotf", "is_on", "power", "control_mode")
    shutter = await _props(instrument, "shutter", "is_open")
    return {
        "on": (laser["is_on"], aotf["is_on"], shutter["is_open"]),
        "power": aotf["power"],
        "controls": (laser["control_mode"], aotf["control_mode"]),
    }


def _saved(instrument: BasicInstrument) -> dict[str, Any]:
    return instrument.view.value.state.profiles["gfp"].model_dump(mode="json", exclude_none=True)["power"]


async def test_a_power_is_saved_for_the_side_the_light_goes_now(instrument: BasicInstrument) -> None:
    await instrument.set_power_mode("full")
    await instrument.set_power("aotf", 35)
    await instrument.set_position_rule("flip", "right")
    await instrument.apply_profile()
    assert (await _light(instrument))["power"] == 42
    await instrument.set_dim_power("aotf", 5)
    assert _saved(instrument) == {
        "laser": {"full": "50 mW"},
        "aotf": {"router": "flip", "full": {"left": "35 %", "right": "42 %"}, "dim": {"left": "3 %", "right": "5 %"}},
    }


async def test_a_power_out_of_range_is_refused_and_nothing_changes(instrument: BasicInstrument) -> None:
    await instrument.set_power_mode("full")
    before = _saved(instrument)
    with pytest.raises(RejectedError, match=r"cannot do 500 % \(it can do 0.5..100 %\)"):
        await instrument.set_power("aotf", 500)
    assert _saved(instrument) == before
    assert (await _light(instrument))["power"] == 30


async def test_the_timelines_of_a_profile_say_what_controls_each_device(instrument: BasicInstrument) -> None:
    assert (await _light(instrument))["controls"] == ("software", "digital")
    await instrument.select_profile("align")
    assert (await _light(instrument))["controls"] == ("software", "software")
    await instrument.select_profile("analog")
    assert (await _light(instrument))["controls"] == ("analog", "digital")
    with pytest.raises(RejectedError, match="A wire sets the power of 'laser'"):
        await instrument.set_power("laser", 20)
