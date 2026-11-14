"""A session on a simulated SPIM microscope whose light comes from a laser head and an AOM, driven only through the
commands an app would call. After each step it prints what an app would see.

Run from the repo root: ``uv run -m illumination_lab.demo``."""

import asyncio
import copy
import logging
import sys
import tempfile
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

from vxl_records import SQLiteRecords

from tests.instruments.spim.support import config_data, simulated, template
from vxl.core.errors import RejectedError
from vxl.core.instrument.folder import InstrumentFolder
from vxl.system import System

from .instrument import LabMicroscope

_DIGITAL = {"kind": "digital", "off": "0 V", "on": "5 V"}


class Session:
    """The SPIM test rig with its laser swapped for a 561 nm head behind an AOM and a shutter; the generator gates the
    AOM. A second profile ``rfp`` is like ``gfp``."""

    def __init__(self, home: Path) -> None:
        data = simulated(config_data())
        data["target"] = "illumination_lab.instrument.LabMicroscope"
        data["devices"]["laser"] = {
            "target": "illumination_lab.devices.SimulatedLaserHead",
            "init": {"wavelength": 561, "low": 1, "high": 100},
        }
        data["devices"]["aom"] = {
            "target": "illumination_lab.devices.SimulatedModulator",
            "init": {"lines": [{"name": "561", "wavelength": 561, "min_transmission": 0.005, "pins": ["ttl_561"]}]},
        }
        data["devices"]["shutter"] = {"target": "illumination_lab.devices.SimulatedShutter"}
        data["optics"]["laser"] = {"to": "aom"}
        data["optics"]["aom"] = {"to": "shutter"}
        data["optics"]["shutter"] = {"to": "galvo"}
        data["wiring"]["ao_main"]["laser"] = {"pin": "ao1", "to": ["aom/ttl_561"], **_DIGITAL}
        profiles = data["default"]["profiles"]
        profiles["rfp"] = copy.deepcopy(profiles["gfp"]) | {"positions": {"fw": "RFP"}}
        folder = InstrumentFolder.create(template(data), "lab", home)
        records = SQLiteRecords(home / "records.sqlite3", resolve_root=lambda spec: home / spec.path.as_posix())
        system = System(store=home / "data", scratch=home / "scratch", remotes={}, max_ram_fraction=0.1)
        self.microscope = LabMicroscope(folder, records=records, system=system)

    async def step(self, what: str, call: Awaitable[Any] | None = None) -> None:
        """Run 1 command, then print what an app would see."""
        print(f"\n> {what}")
        if call is not None:
            try:
                await call
            except RejectedError as error:
                print(f"  refused: {error}")
        m = self.microscope
        laser = await self._props("laser", "is_enabled", "power_mw", "modulation")
        aom = await self._props("aom", "enabled_lines", "transmissions", "modulations")
        shutter = (await self._props("shutter", "is_open"))["is_open"]
        line_open = "561" in aom["enabled_lines"]
        lit = laser["is_enabled"] and line_open and shutter
        sample = laser["power_mw"] * aom["transmissions"]["561"] if lit else 0.0
        powers = {camera: f"{full:g} mW, dim {dim}" for camera, (full, dim) in m.channel_powers().items()}
        activities = [activity.kind for activity in m.activities.value] or "off"
        print(f"  profile {m.active_profile.value}; channel powers {powers}")
        print(f"  preview {activities}; channels {m.preview_channels.value}; light {m.preview_light.value}")
        laser_state = "on" if laser["is_enabled"] else "off"
        print(f"  laser {laser_state}, {laser['power_mw']:g} mW, {str(laser['modulation']).lower()}")
        aom_state = "open" if line_open else "closed"
        mode = str(aom["modulations"]["561"]).lower()
        print(f"  aom/561 {aom_state}, transmission {aom['transmissions']['561']:.3g}, {mode}")
        print(f"  shutter {'open' if shutter else 'closed'}")
        print(f"  power meter: {sample:.3g} mW")

    async def _props(self, device: str, *names: str) -> dict[str, Any]:
        results = await self.microscope.get_device_properties(device, names)
        return {name: results.results[name].unwrap().value for name in names}


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout, format="  note: %(message)s")
    with tempfile.TemporaryDirectory() as tmp:
        session = Session(Path(tmp))
        m = session.microscope
        await session.step("open()", m.open())
        try:
            await session.step('set_channel_power("camera", 10)', m.set_channel_power("camera", 10))
            await session.step('set_channel_dim_power("camera", 1)', m.set_channel_dim_power("camera", 1))
            await session.step("start_preview()", m.start_preview())
            await session.step('set_preview_light("full")', m.set_preview_light("full"))
            await session.step('set_channel_power("camera", 12)', m.set_channel_power("camera", 12))
            await session.step('set_channel_power("camera", 500)', m.set_channel_power("camera", 500))
            await session.step('select_profile("rfp")', m.select_profile("rfp"))
            await session.step('set_channel_power("camera", 3)', m.set_channel_power("camera", 3))
            await session.step('select_profile("gfp")', m.select_profile("gfp"))
            await session.step("stop_preview()", m.stop_preview())
        finally:
            await m.close()


if __name__ == "__main__":
    asyncio.run(main())
