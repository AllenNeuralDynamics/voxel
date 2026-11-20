"""A session on a simulated SPIM microscope that prints the lights after each command.

Run from the repo root: ``uv run -m prototypes.demo``."""

import asyncio
import copy
import logging
import sys
import tempfile
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

from vxl_instruments.spim.instrument import Microscope

from instruments.tests.spim.support import config_data, simulated, template
from vxl.records import Records
from vxl.station.errors import RejectedError
from vxl.station.instrument.folder import InstrumentFolder
from vxl.system import System

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


class Session:
    """The SPIM test rig with a 488 nm laser, 1 AOTF line, a shutter, and a flip mirror that sends the light to the
    left or the right arm, or nowhere when it is ``closed``. The generator can gate the AOTF line and set the laser's
    power.

    It has 3 profiles. ``gfp`` gates the AOTF line with the generator, and gives it 1 power for each side. ``align``
    is the same with no gate signal, for a steady light. ``analog`` also sets the laser's power with a wire."""

    def __init__(self, home: Path) -> None:
        data = simulated(config_data())
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
            "aotf": {
                "router": "flip",
                "full": {"left": "30 %", "right": "42 %"},
                "dim": {"left": "3 %", "right": "4 %"},
            },
        }
        align = copy.deepcopy(gfp)
        del align["timelines"]["ao_main"]["signals"]["gate"]
        analog = copy.deepcopy(gfp)
        analog["timelines"]["ao_main"]["signals"]["laser_power"] = {"kind": "constant", "value": "2 V"}
        del analog["power"]["laser"]
        default["profiles"] |= {"align": align, "analog": analog}
        folder = InstrumentFolder.create(template(data), "lab", home)
        records = Records(home / "records.sqlite3", resolve_root=lambda spec: home / spec.path.as_posix())
        system = System(store=home / "data", scratch=home / "scratch", remotes={}, max_ram_fraction=0.1)
        self.microscope = Microscope(folder, records=records, system=system)

    async def step(self, what: str, *calls: Awaitable[Any]) -> None:
        """Run the commands of 1 step, then print the lights."""
        print(f"\n> {what}")
        for call in calls:
            try:
                await call
            except RejectedError as error:
                print(f"  refused: {error}")
        view = self.microscope.view.value
        laser = await self.props("laser", "is_on", "power", "control_mode")
        aotf = await self.props("aotf", "is_on", "power", "control_mode")
        shutter = await self.props("shutter", "is_open")
        bare = await self.props("laser_561", "is_on")
        activities = [activity.kind for activity in view.activities] or "none"
        side = view.state.positions["flip"]
        print(f"  profile {view.active_profile}; side {side}; power mode {view.power_mode}; running {activities}")
        print(f"  laser   {_on(laser['is_on'])}, {laser['power']:g} mW, control {laser['control_mode']}")
        print(f"  aotf    {_on(aotf['is_on'])}, {aotf['power']:g} %, control {aotf['control_mode']}")
        print(f"  shutter {'open' if shutter['is_open'] else 'closed'}")
        print(f"  laser_561 {_on(bare['is_on'])} (nothing after it stops its light)")

    async def props(self, device: str, *names: str) -> dict[str, Any]:
        """The values of some properties of a device, read now."""
        results = await self.microscope.get_device_properties(device, names)
        return {name: results.results[name].unwrap().value for name in names}


def _on(value: bool) -> str:
    return "on " if value else "off"


async def main() -> None:
    logging.basicConfig(level=logging.CRITICAL, stream=sys.stdout)
    with tempfile.TemporaryDirectory() as tmp:
        session = Session(Path(tmp))
        m = session.microscope
        await session.step("open()", m.open())
        try:
            await session.step('execute_device_command("laser_561", "on")', m.execute_device_command("laser_561", "on"))
            await session.step("start_preview()", m.start_preview())
            await session.step('set_power_mode("full")', m.set_power_mode("full"))
            await session.step('set_power("aotf", 35)', m.set_power("aotf", 35))
            await session.step('set_power("aotf", 500)', m.set_power("aotf", 500))
            await session.step(
                'set_position_rule("flip", "right"), apply_profile()',
                m.set_position_rule("flip", "right"),
                m.apply_profile(),
            )
            await session.step(
                'set_dim_power("aotf", 5), set_power_mode("dim")',
                m.set_dim_power("aotf", 5),
                m.set_power_mode("dim"),
            )
            await session.step(
                'set_position_rule("flip", "closed"), apply_profile()',
                m.set_position_rule("flip", "closed"),
                m.apply_profile(),
            )
            await session.step(
                'set_position_rule("flip", "right"), apply_profile()',
                m.set_position_rule("flip", "right"),
                m.apply_profile(),
            )
            await session.step('select_profile("align")', m.select_profile("align"))
            await session.step('select_profile("analog")', m.select_profile("analog"))
            await session.step('set_power("laser", 20)', m.set_power("laser", 20))
            await session.step("lights_off()", m.lights_off())
            await session.step("lasers_off()", m.lasers_off())
            await session.step("stop_preview()", m.stop_preview())
            saved = m.view.value.state.profiles["gfp"].model_dump(mode="json", exclude_none=True)["power"]
            print(f"\nthe gfp profile's saved power: {saved}")
        finally:
            await m.close()


if __name__ == "__main__":
    asyncio.run(main())
