import time

import numpy as np
import pytest

from tests.devices.camera.hamamatsu.conftest import HAMAMATSU_SERIAL_NUMBER, HAMAMATSU_CAMERA_ID
from voxel.instrument.drivers.camera.hamamatsu.definitions import (
    Binning,
    PixelType,
    SensorMode,
    ReadoutDirection,
    TriggerMode,
    TriggerSource,
    TriggerPolarity,
    TriggerActive,
)


def test_camera_initialization(real_camera):
    assert real_camera.name == HAMAMATSU_CAMERA_ID
    assert real_camera.serial_number == HAMAMATSU_SERIAL_NUMBER


def test_sensor_size(real_camera):
    assert real_camera.sensor_width_px > 0
    assert real_camera.sensor_height_px > 0


def test_roi_settings(real_camera):
    original_width = real_camera.roi_width_px
    original_height = real_camera.roi_height_px
    step_width = real_camera.roi_width_px.step

    new_width = original_width // 2
    new_height = original_height // 2

    real_camera.roi_width_px = new_width
    real_camera.roi_height_px = new_height

    expected_width = new_width - (new_width % step_width)
    expected_height = new_height - (new_height % step_width)

    assert real_camera.roi_width_px == expected_width
    assert real_camera.roi_height_px == expected_height

    real_camera.roi_width_px = original_width
    real_camera.roi_height_px = original_height

    assert real_camera.roi_width_px == original_width
    assert real_camera.roi_height_px == original_height


def test_exposure_time(real_camera):
    original_exposure = real_camera.exposure_time_ms
    minimum = real_camera.exposure_time_ms.minimum
    maximum = real_camera.exposure_time_ms.maximum
    step = real_camera.exposure_time_ms.step
    new_exposure = round((minimum + maximum) / 2 / step) * step

    real_camera.exposure_time_ms = new_exposure
    assert abs(real_camera.exposure_time_ms - new_exposure) < 1  # Allow for small rounding errors

    real_camera.exposure_time_ms = original_exposure


def test_binning(real_camera):
    original_binning = real_camera.binning
    options = real_camera.binning.options

    for option in options:
        assert type(option) == Binning
        real_camera.binning = option
        assert real_camera.binning == option

    real_camera.binning = original_binning
    print(type(original_binning.value))
    print(original_binning.value)
    assert real_camera.binning == original_binning.value


def test_pixel_type(real_camera):
    original_pixel_type = real_camera.pixel_type
    options = real_camera.pixel_type.options

    for option in options:
        assert type(option) == PixelType
        real_camera.pixel_type = option
        assert real_camera.pixel_type == option

    real_camera.pixel_type = original_pixel_type


def test_sensor_mode(real_camera):
    original_sensor_mode = real_camera.sensor_mode
    options = real_camera.sensor_mode.options

    for option in options:
        assert type(option) == SensorMode
        real_camera.sensor_mode = option
        assert real_camera.sensor_mode == option

    real_camera.sensor_mode = original_sensor_mode
    assert real_camera.sensor_mode == original_sensor_mode


def test_readout_direction(real_camera):
    original_readout_direction = real_camera.readout_direction
    options = real_camera.readout_direction.options

    for option in options:
        assert type(option) == ReadoutDirection
        real_camera.readout_direction = option
        assert real_camera.readout_direction == option

    real_camera.readout_direction = original_readout_direction


def test_trigger_settings(real_camera):
    original_trigger_mode = real_camera.trigger_mode
    original_trigger_source = real_camera.trigger_source
    original_trigger_polarity = real_camera.trigger_polarity
    original_trigger_active = real_camera.trigger_active

    trigger_mode_options = real_camera.trigger_mode.options
    for mode in trigger_mode_options:
        assert type(mode) == TriggerMode
        real_camera.trigger_mode = mode
        assert real_camera.trigger_mode == mode or mode not in real_camera.trigger_mode.options

        trigger_source_options = real_camera.trigger_source.options
        for source in trigger_source_options:
            assert type(source) == TriggerSource
            real_camera.trigger_source = source
            assert real_camera.trigger_source == source or source not in real_camera.trigger_source.options

            trigger_polarity_options = real_camera.trigger_polarity.options
            for polarity in trigger_polarity_options:
                assert type(polarity) == TriggerPolarity
                real_camera.trigger_polarity = polarity
                assert real_camera.trigger_polarity == polarity or polarity not in real_camera.trigger_polarity.options

                trigger_active_options = real_camera.trigger_active.options
                for active in trigger_active_options:
                    assert type(active) == TriggerActive
                    real_camera.trigger_active = active
                    assert real_camera.trigger_active == active or active not in real_camera.trigger_active.options

    real_camera.trigger_mode = original_trigger_mode
    real_camera.trigger_source = original_trigger_source
    real_camera.trigger_polarity = original_trigger_polarity
    real_camera.trigger_active = original_trigger_active


def test_acquisition(real_camera):
    real_camera.prepare()
    real_camera.start()

    time.sleep(1)  # Allow some time for frames to be captured

    frame = real_camera.grab_frame()
    assert frame is not None
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (real_camera.roi_height_px, real_camera.roi_width_px)

    state = real_camera.acquisition_state
    assert state.frame_index > 0
    assert state.frame_rate_fps > 0

    real_camera.stop()


def test_log_metadata(real_camera):
    real_camera.log_metadata()
    # This test doesn't assert anything, but it ensures the method runs without errors


# Add more hardware tests as needed

if __name__ == "__main__":
    pytest.main([__file__])
