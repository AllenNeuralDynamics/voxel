import math

import pytest
from pydantic import ValidationError
from rigup.config import DeviceConfig
from rigup.node import LocalNode
from vxlib.units import Frequency
from vxlib.vector import Span

from vxl.devices.signals.cards.simulated import SimulatedDaqmx
from vxl.devices.signals.generator.base import Cycle, GeneratorController, InputEdges, OwnClock
from vxl.devices.signals.generator.handle import GeneratorHandle
from vxl.devices.signals.generator.simulated import SimulatedGenerator


def _cycle(volts: dict[str, list[float]] | None = None, start: OwnClock | InputEdges | None = None) -> Cycle:
    return Cycle(
        sample_rate=Frequency("1 kHz"),
        volts=volts or {"ao0": [0.0, 5.0, 5.0, 0.0], "ao1": [1.0, 1.0, -1.0, -1.0]},
        start=start or OwnClock(),
    )


def _controller() -> tuple[SimulatedDaqmx, SimulatedGenerator, GeneratorController]:
    hub = SimulatedDaqmx(num_ao=4, num_pfi=2, num_counters=1)
    generator = SimulatedGenerator("gen", hub=hub)
    return hub, generator, GeneratorController(generator)


@pytest.mark.parametrize(
    ("volts", "match"),
    [
        ({"ao0": [0.0, 1.0], "ao1": [0.0]}, "same number of samples"),
        ({"ao0": []}, "same number of samples"),
        ({"ao0": [0.0, math.nan]}, "finite"),
        ({}, "at least 1"),
    ],
)
def test_a_cycle_has_finite_samples_of_1_length_on_every_pin(volts: dict[str, list[float]], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Cycle(sample_rate=Frequency("1 kHz"), volts=volts, start=OwnClock())


def test_a_cycle_counts_its_samples() -> None:
    assert _cycle().samples == 4


async def test_loading_arms_the_cycle_and_reserves_its_pins() -> None:
    hub, generator, controller = _controller()
    cycle = _cycle(start=InputEdges(pin="pfi0"))
    await controller.load(cycle)
    assert (controller.state, controller.loaded, generator.armed) == ("loaded", cycle, cycle)
    assert set(hub.assigned_pins) == {"ao0", "ao1", "pfi0"}


async def test_a_new_cycle_while_running_keeps_running_with_only_its_own_pins() -> None:
    hub, generator, controller = _controller()
    await controller.load(_cycle())
    await controller.start()
    await controller.load(_cycle({"ao2": [0.0, 1.0]}))
    assert (controller.state, generator.running) == ("running", True)
    assert set(hub.assigned_pins) == {"ao2"}


async def test_a_counted_run_ends_by_itself() -> None:
    _, generator, controller = _controller()
    await controller.load(_cycle())
    await controller.start(count=3)  # 3 cycles of 4 samples at 1 kHz: 12 ms
    await controller.wait_until_done(timeout_s=1.0)
    assert (controller.state, generator.running) == ("loaded", False)


async def test_what_a_generator_cannot_do_is_refused() -> None:
    _, _, controller = _controller()
    with pytest.raises(RuntimeError, match="load one first"):
        await controller.start()
    with pytest.raises(ValueError, match="no output pins"):
        await controller.load(_cycle({"ao9": [0.0]}))
    await controller.load(_cycle(start=InputEdges(pin="pfi0")))
    with pytest.raises(NotImplementedError, match="cannot count"):
        await controller.start(count=2)


async def test_a_failed_load_leaves_the_generator_empty() -> None:
    hub, _, controller = _controller()
    hub.assign_pin("other", "ao1")
    with pytest.raises(ValueError, match="already assigned"):
        await controller.load(_cycle())
    assert (controller.state, controller.loaded) == ("empty", None)
    assert hub.assigned_pins == {"ao1": "other"}


async def test_a_cycle_crosses_a_rig_node_intact() -> None:
    node = LocalNode(node_id="test")
    configs = {
        "card": DeviceConfig(target="vxl.devices.signals.cards.simulated.SimulatedDaqmx", init={"num_ao": 4}),
        "gen": DeviceConfig(target="vxl.devices.signals.generator.simulated.SimulatedGenerator", init={"hub": "card"}),
    }
    handles, errors = await node.build_devices(configs)
    assert errors == {}
    generator = GeneratorHandle.wrap(handles["gen"])
    try:
        await generator.load(_cycle())
        assert await generator.get_loaded() == _cycle()
        pins = await generator.pins.get()
        assert [pin.name for pin in pins if pin.sends] == ["ao0", "ao1", "ao2", "ao3"]
        assert {pin.kind for pin in pins if pin.receives} == {"digital"}
        assert isinstance(await generator.get_voltage_range(), Span)
        assert await generator.state.get() == "loaded"
    finally:
        await node.close()
