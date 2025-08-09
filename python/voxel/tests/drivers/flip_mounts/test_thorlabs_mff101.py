import time

import pytest

from tests.drivers.conftest import get_env
from voxel.instrument.drivers.flip_mount.thorlabs_mff101 import FLIP_TIME_RANGE_MS, ThorlabsFlipMount

CONN = get_env("THORLABS_FLIPMOUNT_CONN")
POSITION_1 = "A"
POSITION_2 = "B"
WRONG_POSITION = "C"


@pytest.fixture
def thorlabs_mff101():
    fm = ThorlabsFlipMount(
        name="flip-mount-1",
        conn=CONN,
        position_1=POSITION_1,
        position_2=POSITION_2,
    )
    yield fm
    fm.close()


def test_connect(thorlabs_mff101):
    assert thorlabs_mff101._inst is not None
    thorlabs_mff101.wait()
    assert thorlabs_mff101.position == POSITION_1


def test_close(thorlabs_mff101):
    thorlabs_mff101.close()
    assert thorlabs_mff101._inst is None


def test_position(thorlabs_mff101):
    thorlabs_mff101.wait()
    assert thorlabs_mff101.position == POSITION_1

    thorlabs_mff101.position = POSITION_2
    thorlabs_mff101.wait()
    assert thorlabs_mff101.position == POSITION_2

    thorlabs_mff101.position = POSITION_1
    thorlabs_mff101.wait()
    assert thorlabs_mff101.position == POSITION_2


def test_toggle(thorlabs_mff101):
    thorlabs_mff101.wait()
    assert thorlabs_mff101.position == POSITION_1

    thorlabs_mff101.toggle(wait=True)
    assert thorlabs_mff101.position == POSITION_2

    thorlabs_mff101.toggle(wait=True)
    assert thorlabs_mff101.position == POSITION_1


def test_invalid_position(thorlabs_mff101):
    with pytest.raises(ValueError):
        thorlabs_mff101.position = WRONG_POSITION


def test_flip_time_ms(thorlabs_mff101):
    assert thorlabs_mff101.flip_time_ms == 1000.0  # default switch time
    thorlabs_mff101.flip_time_ms = 500.0
    assert thorlabs_mff101.flip_time_ms == 500.0
    thorlabs_mff101.flip_time_ms = 1000.0
    assert thorlabs_mff101.flip_time_ms == 1000.0


def test_invalid_flip_time(thorlabs_mff101):
    # test lower bound
    thorlabs_mff101.flip_time_ms = FLIP_TIME_RANGE_MS[0] - 0.1
    assert thorlabs_mff101.flip_time_ms == FLIP_TIME_RANGE_MS[0]
    # test upper bound
    thorlabs_mff101.flip_time_ms = FLIP_TIME_RANGE_MS[1] + 1
    assert thorlabs_mff101.flip_time_ms == FLIP_TIME_RANGE_MS[1]


def test_different_switch_times(thorlabs_mff101):
    thorlabs_mff101.position = POSITION_1
    thorlabs_mff101.wait()

    cycles = 5
    switch_times = [500, 1000, 1500, 2000, 2800]
    for switch_time in switch_times:
        thorlabs_mff101.flip_time_ms = switch_time
        for _ in range(cycles):
            time.sleep(1)
            thorlabs_mff101.toggle(wait=True)
            assert thorlabs_mff101.position == POSITION_2

            time.sleep(1)
            thorlabs_mff101.toggle(wait=True)
            assert thorlabs_mff101.position == POSITION_1
