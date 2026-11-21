from collections.abc import Callable

import pytest

from vxl.devices.axes.simulated import SimulatedDiscreteAxis
from vxl.devices.camera.simulated.simulated import SimulatedCamera
from vxl.parts import Filter


@pytest.mark.parametrize("delay", [-1.0, float("inf"), float("nan")])
@pytest.mark.parametrize(
    "create_device",
    [
        pytest.param(lambda delay: SimulatedCamera("camera", start_delay_s=delay), id="camera-start"),
        pytest.param(lambda delay: SimulatedCamera("camera", stop_delay_s=delay), id="camera-stop"),
        pytest.param(
            lambda delay: SimulatedDiscreteAxis("selector", slots={0: "left", 1: "right"}, settle_seconds=delay),
            id="discrete-settle",
        ),
    ],
)
def test_simulated_device_rejects_invalid_delays(create_device: Callable[[float], object], delay: float) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        create_device(delay)


def test_a_slot_that_holds_a_part_takes_its_name() -> None:
    glass = Filter.model_validate({"id": "BP525", "band": ["500 nm", "550 nm"]})

    wheel = SimulatedDiscreteAxis(device_id="fw", slots={0: glass, 1: "empty"}, settle_seconds=0)

    assert wheel.labels == {0: "BP525", 1: "empty"}
    wheel.move_to("BP525", wait=True)
    assert (wheel.state.position, wheel.state.slot) == ("BP525", 0)
