"""A discrete axis that selects a slot by pulsing 1 on-demand output per slot."""

import pytest

from vxl.devices.axes.discrete.pulse import PulseDiscreteAxis
from vxl.devices.signals.cards.simulated import SimulatedDaqmx
from vxl.devices.signals.on_demand.simulated import SimulatedOnDemandAO, SimulatedOnDemandDO


def test_a_move_pulses_only_its_slots_line_and_leaves_every_line_at_rest() -> None:
    lines = SimulatedOnDemandDO("lines", hub=SimulatedDaqmx("hub"), lines={"0": "port0/line0", "1": "port0/line1"})
    axis = PulseDiscreteAxis("wheel", generator=lines, slots={0: "GFP", 1: "RFP"})

    axis.move_to("RFP", wait=True)

    assert axis.state.target == 1
    assert lines.states == {"0": False, "1": False}


def test_analog_outputs_rest_at_0_v_after_a_pulse() -> None:
    ports = SimulatedOnDemandAO("ports", hub=SimulatedDaqmx("hub"), ports={"0": "ao6", "1": "ao7"})
    axis = PulseDiscreteAxis("wheel", generator=ports, slots={0: "GFP", 1: "RFP"})

    axis.move_to_slot(0, wait=True)

    assert ports.levels == {"0": pytest.approx(0.0), "1": pytest.approx(0.0)}
