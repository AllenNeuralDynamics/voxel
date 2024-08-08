import pytest
import time
from voxel.devices.rotation_axis.simulated import SimulatedRotationAxis


@pytest.fixture
def sim_axis():
    axis = SimulatedRotationAxis("test_axis")
    yield axis
    axis.close()


def test_initial_state(sim_axis):
    assert sim_axis.position_deg == 0.0
    assert sim_axis.speed_deg_s == 10.0
    assert not sim_axis.is_moving


def test_move_and_wait(sim_axis):
    sim_axis.position_deg = 90.0
    sim_axis.wait_until_stopped()
    assert pytest.approx(sim_axis.position_deg, 0.01) == 90.0
    assert not sim_axis.is_moving


def test_speed_change(sim_axis):
    sim_axis.speed_deg_s = 20.0
    assert sim_axis.speed_deg_s == 20.0
    sim_axis.position_deg = 180.0
    start_time = time.time()
    sim_axis.wait_until_stopped()
    end_time = time.time()
    assert pytest.approx(end_time - start_time, 0.1) == 180.0 / 20.0


def test_continuous_movement(sim_axis):
    sim_axis.position_deg = 45.0
    time.sleep(2)  # Wait for 2 seconds
    current_pos = sim_axis.position_deg
    assert 0.0 < current_pos < 45.0
    sim_axis.wait_until_stopped()
    assert pytest.approx(sim_axis.position_deg, 0.01) == 45.0


def test_change_direction(sim_axis):
    sim_axis.position_deg = 90.0
    time.sleep(1)
    sim_axis.position_deg = 0.0
    sim_axis.wait_until_stopped()
    assert pytest.approx(sim_axis.position_deg, 0.01) == 0.0


def test_multiple_movements(sim_axis):
    positions = [30.0, 60.0, 90.0, 120.0]
    for pos in positions:
        sim_axis.position_deg = pos
        sim_axis.wait_until_stopped()
        assert pytest.approx(sim_axis.position_deg, 0.01) == pos


def test_speed_limits(sim_axis):
    with pytest.raises(ValueError):
        sim_axis.speed_deg_s = 0.0
    with pytest.raises(ValueError):
        sim_axis.speed_deg_s = -5.0


def test_movement_precision(sim_axis):
    sim_axis.speed_deg_s = 1.0  # Slow speed for precision test
    sim_axis.position_deg = 1.0
    sim_axis.wait_until_stopped()
    assert pytest.approx(sim_axis.position_deg, 0.001) == 1.0
