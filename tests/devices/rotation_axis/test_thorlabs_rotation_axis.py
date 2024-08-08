from unittest.mock import Mock, patch

import pytest

from voxel.devices.rotation_axis.thorlabs import ThorlabsRotationAxis

# This flag determines whether to use a mock device or real hardware
USE_MOCK_DEVICE = True

ACTUAL_SERIAL_NUMBER = "THE_SERIAL_NUMBER"


@pytest.fixture
def thorlabs_axis():
    if USE_MOCK_DEVICE:
        with patch('voxel.devices.rotation_axis.thorlabs.Thorlabs') as mock_thorlabs:
            mock_instance = Mock()
            mock_thorlabs.list_kinesis_devices.return_value = [('COM1', 'Device1')]
            mock_thorlabs.Kinesis.return_value = mock_instance
            mock_instance.get_device_info.return_value = Mock(serial_no='TEST123')

            # Set up mock methods for position, speed, and movement
            mock_instance.get_position.return_value = 0.0
            mock_instance.get_velocity_parameters.return_value = Mock(max_velocity=10.0)
            mock_instance.get_status.return_value = Mock(is_moving=False)

            axis = ThorlabsRotationAxis("test_id", "TEST123")
            yield axis
    else:
        axis = ThorlabsRotationAxis("test_id", ACTUAL_SERIAL_NUMBER)
        yield axis

    axis.close()


def test_initialization(thorlabs_axis):
    assert thorlabs_axis.id == "test_id"
    assert thorlabs_axis.serial_number in ["TEST123", ACTUAL_SERIAL_NUMBER]


def test_get_set_position(thorlabs_axis):
    if USE_MOCK_DEVICE:
        thorlabs_axis._instance.get_position.return_value = 0.0
    initial_pos = thorlabs_axis.position_deg
    new_pos = (initial_pos + 10) % 360
    thorlabs_axis.position_deg = new_pos
    if USE_MOCK_DEVICE:
        thorlabs_axis._instance.get_position.return_value = new_pos
    thorlabs_axis.wait_until_stopped()
    assert pytest.approx(thorlabs_axis.position_deg, 0.1) == new_pos


def test_get_set_speed(thorlabs_axis):
    if USE_MOCK_DEVICE:
        thorlabs_axis._instance.get_velocity_parameters.return_value = Mock(max_velocity=10.0)
    initial_speed = thorlabs_axis.speed_deg_s
    new_speed = min(max(initial_speed + 1, 0.005), 10)
    thorlabs_axis.speed_deg_s = new_speed
    if USE_MOCK_DEVICE:
        thorlabs_axis._instance.get_velocity_parameters.return_value = Mock(max_velocity=new_speed)
    assert pytest.approx(thorlabs_axis.speed_deg_s, 0.1) == new_speed


def test_movement(thorlabs_axis):
    if USE_MOCK_DEVICE:
        thorlabs_axis._instance.get_position.return_value = 0.0
        thorlabs_axis._instance.get_status.return_value = Mock(is_moving=True)
    start_pos = thorlabs_axis.position_deg
    target_pos = (start_pos + 45) % 360
    thorlabs_axis.position_deg = target_pos
    assert thorlabs_axis.is_moving
    if USE_MOCK_DEVICE:
        thorlabs_axis._instance.get_status.return_value = Mock(is_moving=False)
        thorlabs_axis._instance.get_position.return_value = target_pos
    thorlabs_axis.wait_until_stopped()
    assert not thorlabs_axis.is_moving
    assert pytest.approx(thorlabs_axis.position_deg, 0.1) == target_pos


def test_speed_limits(thorlabs_axis):
    with pytest.raises(ValueError):
        thorlabs_axis.speed_deg_s = 0.0
    with pytest.raises(ValueError):
        thorlabs_axis.speed_deg_s = 11.0


@pytest.mark.skipif(USE_MOCK_DEVICE, reason="This test requires real hardware")
def test_real_hardware_specific(thorlabs_axis):
    # This test will only run on real hardware
    # Add any tests that specifically require real hardware here
    pass
