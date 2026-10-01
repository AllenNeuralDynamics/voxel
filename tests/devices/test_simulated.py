from collections.abc import Callable

import pytest

from vxl.devices.camera.simulated.simulated import SimulatedCamera
from vxl.devices.laser.simulated import SimulatedLaser


@pytest.mark.parametrize("delay", [-1.0, float("inf"), float("nan")])
@pytest.mark.parametrize(
    "create_device",
    [
        pytest.param(lambda delay: SimulatedCamera("camera", start_delay_s=delay), id="camera-start"),
        pytest.param(lambda delay: SimulatedCamera("camera", stop_delay_s=delay), id="camera-stop"),
        pytest.param(lambda delay: SimulatedLaser("laser", wavelength=488, enable_delay_s=delay), id="laser-enable"),
    ],
)
def test_simulated_device_rejects_invalid_delays(create_device: Callable[[float], object], delay: float) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        create_device(delay)
