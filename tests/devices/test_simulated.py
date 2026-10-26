from collections.abc import Callable

import pytest

from vxl.devices.axes.simulated import SimulatedDiscreteAxis
from vxl.devices.camera.simulated.simulated import SimulatedCamera
from vxl.devices.laser.simulated import SimulatedLaser
from vxl.devices.laser.source import ModulationMode


def test_laser_rejects_unsupported_modulation_mode() -> None:
    laser = SimulatedLaser("laser", wavelength=488, modulation_modes=(ModulationMode.SOFTWARE,))
    with pytest.raises(ValueError, match="Unsupported modulation mode"):
        laser.set_modulation_mode(ModulationMode.DIGITAL)
    assert laser.modulation_mode == ModulationMode.SOFTWARE


@pytest.mark.parametrize("mode", list(ModulationMode))
def test_laser_startup_preserves_deadline_and_waits_only_for_remaining_time(
    monkeypatch: pytest.MonkeyPatch, mode: ModulationMode
) -> None:
    now = 0.0
    waits = []

    def sleep(seconds):
        nonlocal now
        waits.append(seconds)
        now += seconds

    monkeypatch.setattr("vxl.devices.laser.simulated.monotonic", lambda: now)
    monkeypatch.setattr("vxl.devices.laser.simulated.sleep", sleep)
    laser = SimulatedLaser("laser", wavelength=488, source_enable_delay_s=5, power_noise_percent=0)
    laser.set_modulation_mode(mode)
    laser.source_power_setpoint_mw = 40
    laser.output_level_percent = 50
    laser.source_enable()
    laser.output_enable()
    assert laser.is_source_enabled
    assert laser.is_output_enabled
    assert laser.source_power_mw == laser.output_power_mw == 0
    assert not waits
    now = 2
    laser.source_enable(wait=True)
    assert waits == [3]
    assert laser.output_power_mw == 20
    laser.output_enable(wait=True)
    assert waits == [3]

    laser.source_disable()
    laser.source_enable()
    now += 1
    laser.output_enable(wait=True)
    assert waits == [3, 4]
    assert laser.source_power_mw == 40
    laser.output_level_percent = 25
    assert laser.output_power_mw == 10
    laser.output_disable()
    assert laser.output_power_mw == 0
    assert laser.source_power_mw == 40


def test_laser_power_noise_is_relative_and_sampled_per_read(monkeypatch: pytest.MonkeyPatch) -> None:
    samples = iter([1, -1, 1])
    monkeypatch.setattr("vxl.devices.laser.simulated.gauss", lambda mean, sigma: mean + sigma * next(samples))
    laser = SimulatedLaser("laser", wavelength=488, power_noise_percent=1)
    laser.source_power_setpoint_mw = 40
    laser.output_level_percent = 25
    assert laser.source_power_mw == 0
    laser.source_enable()
    assert laser.source_power_mw == pytest.approx(40.4)
    assert laser.source_power_mw == pytest.approx(39.6)
    assert laser.output_power_mw == 0
    laser.output_enable()
    assert laser.output_power_mw == pytest.approx(10.1)


@pytest.mark.parametrize("noise", [-1.0, float("inf"), float("nan")])
def test_laser_rejects_invalid_power_noise(noise: float) -> None:
    with pytest.raises(ValueError, match="power_noise_percent must be finite and non-negative"):
        SimulatedLaser("laser", wavelength=488, power_noise_percent=noise)


@pytest.mark.parametrize("delay", [-1.0, float("inf"), float("nan")])
@pytest.mark.parametrize(
    "create_device",
    [
        pytest.param(
            lambda delay: SimulatedLaser("laser", wavelength=488, source_enable_delay_s=delay), id="laser-source"
        ),
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
