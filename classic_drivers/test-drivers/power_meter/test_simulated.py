import pytest

from voxel.instrument.drivers.power_meter.simulated import SimulatedPowerMeter


@pytest.fixture
def power_meter():
    pm = SimulatedPowerMeter(name="simulated-pm", wavelength_nm=538)
    yield pm
    pm.close()


def test_power_nm(power_meter):
    power = power_meter.power_mw
    assert 0 <= power <= 1000


def test_wavelength_nm(power_meter) -> None:
    assert power_meter.wavelength_nm == 538


def test_set_wavelength_nm(power_meter) -> None:
    power_meter.wavelength_nm = 532
    assert power_meter.wavelength_nm == 532


def test_close(power_meter) -> None:
    power_meter.close()
    with pytest.raises(Exception):
        power = power_meter.power_mw
    with pytest.raises(Exception):
        wavelength = power_meter.wavelength_nm
    with pytest.raises(Exception):
        power_meter.wavelength_nm = 532
