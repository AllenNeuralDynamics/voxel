from collections.abc import AsyncIterator

import pytest
from rigup.config import DeviceConfig
from rigup.node import LocalNode
from vxlib.vector import Span

from vxl.devices.light.laser import LaserHandle
from vxl.devices.light.modulator import ModulatorHandle

_SIMULATED = "vxl.devices.light.simulated"

type Lights = tuple[LaserHandle, ModulatorHandle]


@pytest.fixture
async def lights() -> AsyncIterator[Lights]:
    """A laser with a digital and an analog pin, and a modulator with only a digital pin, on a rig node."""
    node = LocalNode(node_id="test")
    configs = {
        "laser": DeviceConfig(target=f"{_SIMULATED}.SimulatedLaser", init={"wavelength": 488}),
        "aotf": DeviceConfig(target=f"{_SIMULATED}.SimulatedModulator", init={"pins": ["ttl_in"]}),
    }
    handles, errors = await node.build_devices(configs)
    assert errors == {}
    yield LaserHandle.wrap(handles["laser"]), ModulatorHandle.wrap(handles["aotf"])
    await node.close()


async def test_each_kind_shows_its_unit_and_range_across_a_rig_node(lights: Lights) -> None:
    laser, aotf = lights
    for handle, unit in ((laser, "mW"), (aotf, "%")):
        properties = (await handle.interface()).props
        assert [properties[name].units for name in ("power", "power_range")] == [unit, unit]
    assert await laser.power_range.get() == Span(1, 100)
    assert await aotf.power_range.get() == Span(0.5, 100)
    assert await laser.get_wavelength() == 488


async def test_a_power_out_of_range_is_refused_and_the_power_stays(lights: Lights) -> None:
    laser, _ = lights
    await laser.set_power(50)
    with pytest.raises(RuntimeError, match="cannot do 500"):
        await laser.set_power(500)
    assert await laser.power.get() == 50


async def test_a_control_mode_needs_a_pin_for_it(lights: Lights) -> None:
    laser, aotf = lights
    await laser.set_control_mode("mixed")
    await aotf.set_control_mode("digital")
    with pytest.raises(RuntimeError, match="no analog pin"):
        await aotf.set_control_mode("mixed")
    assert await aotf.control_mode.get() == "digital"
