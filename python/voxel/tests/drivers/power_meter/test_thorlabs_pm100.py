import time

import pytest

from voxel.instrument.drivers import ThorlabsPowerMeter

STRESS_TEST_MINUTES = 1


@pytest.fixture
def pm100d():
    pm = ThorlabsPowerMeter(id="pm100d", conn="USB0::0x1313::0x8078::P0008860::INSTR")
    yield pm
    pm.close()


def test_power_nm(pm100d: ThorlabsPowerMeter) -> None:
    power_mw = pm100d.power_mw
    assert isinstance(power_mw, float)
    assert power_mw > 0


def test_wavelength_nm(pm100d: ThorlabsPowerMeter) -> None:
    wavelength_nm = pm100d.wavelength_nm
    assert isinstance(wavelength_nm, float)
    assert wavelength_nm > 0


def test_set_wavelength_nm(pm100d: ThorlabsPowerMeter) -> None:
    pm100d.wavelength_nm = 532
    assert pm100d.wavelength_nm == 532


@pytest.mark.stress
def test_extended_data_collection(pm100d) -> None:
    """
    Stress test for the power meter device. Collect data for extended period of time.
    To run this test, use the following command:
        pytest ./test_thorlabs_pm100.py -m "stress" -o log_cli=true -o log_cli_level=INFO
    command should be run from the tests/devices/power_meter directory.
    """
    pm100d.log.info(f"Starting stress test for {STRESS_TEST_MINUTES} minutes")
    start_time = time.time()
    duration = STRESS_TEST_MINUTES * 60  # in seconds
    while time.time() - start_time < duration:
        power = pm100d.power_mw
        remaining_time = duration - (time.time() - start_time)
        pm100d.log.info(f"Power: {power} mW, Time Remaining: {remaining_time} seconds")
        assert 0 <= power <= 1000
        time.sleep(1)  # wait for 1 second before the next data collection
