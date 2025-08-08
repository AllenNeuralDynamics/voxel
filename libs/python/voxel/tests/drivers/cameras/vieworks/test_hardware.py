import pytest

from tests.devices.camera.vieworks.conftest import CAMERA_1_SN, CAMERA_2_SN
from voxel.instrument.drivers.camera.vieworks.definitions import (
    Binning,
    PixelType,
    BitPackingMode,
    TriggerMode,
    TriggerSource,
    TriggerPolarity,
)


def test_camera_initialization(real_camera):
    assert real_camera.name == "real_camera"
    assert real_camera.serial_number == CAMERA_1_SN


def test_multiple_cameras():
    from voxel.instrument.drivers.camera.vieworks import VieworksCamera

    camera1 = VieworksCamera("camera1", CAMERA_1_SN)
    camera2 = VieworksCamera("camera2", CAMERA_2_SN)

    assert camera1.gentl == camera2.gentl

    camera1.close()

    camera3 = VieworksCamera("camera3", CAMERA_1_SN)
    assert camera3.gentl == camera2.gentl

    camera3.close()

    camera2.close()


def test_sensor_size(real_camera):
    assert real_camera.sensor_width_px > 0
    assert real_camera.sensor_height_px > 0


def test_roi_settings(real_camera):
    real_camera.reset_roi()
    original_width = real_camera.roi_width_px
    original_height = real_camera.roi_height_px
    step_width = real_camera.roi_width_px.step

    new_width = original_width // 2
    new_height = original_height // 2

    real_camera.roi_width_px = new_width
    real_camera.roi_height_px = new_height

    expected_width = round(new_width / step_width) * step_width if step_width else new_width
    expected_height = round(new_height / step_width) * step_width if step_width else new_height

    assert abs(real_camera.roi_width_px - expected_width) < step_width
    assert abs(real_camera.roi_height_px - expected_height) < step_width

    real_camera.roi_width_px = original_width
    real_camera.roi_height_px = original_height

    assert real_camera.roi_width_px == original_width
    assert real_camera.roi_height_px == original_height


def test_exposure_time(real_camera):
    original_exposure = real_camera.exposure_time_ms
    minimum = real_camera.exposure_time_ms.minimum
    maximum = real_camera.exposure_time_ms.maximum
    step = real_camera.exposure_time_ms.step
    new_exposure = (minimum + maximum) / 2
    new_exposure = round(new_exposure / step) * step if step else new_exposure

    real_camera.exposure_time_ms = new_exposure
    assert abs(real_camera.exposure_time_ms - new_exposure) < 1  # Allow for small rounding errors

    real_camera.exposure_time_ms = original_exposure


def test_binning(real_camera):
    original_binning = real_camera.binning
    options = real_camera.binning.options

    for option in options:
        assert isinstance(option, Binning)
        real_camera.binning = option
        assert real_camera.binning == option

    real_camera.binning = original_binning
    assert real_camera.binning == original_binning


def test_pixel_type(real_camera):
    original_pixel_type = real_camera.pixel_type
    options = real_camera.pixel_type.options

    for option in options:
        assert isinstance(option, PixelType)
        real_camera.pixel_type = option
        assert real_camera.pixel_type == option

    real_camera.pixel_type = original_pixel_type


def test_bit_packing_mode(real_camera):
    original_bit_packing_mode = real_camera.bit_packing_mode
    options = real_camera.bit_packing_mode.options

    for option in options:
        assert isinstance(option, BitPackingMode)
        real_camera.bit_packing_mode = option
        assert real_camera.bit_packing_mode == option

    real_camera.bit_packing_mode = original_bit_packing_mode


def test_trigger_settings(real_camera):
    original_trigger_mode = real_camera.trigger_mode
    original_trigger_source = real_camera.trigger_source
    original_trigger_polarity = real_camera.trigger_polarity

    trigger_mode_options = real_camera.trigger_mode.options
    for mode in trigger_mode_options:
        assert isinstance(mode, TriggerMode)
        real_camera.trigger_mode = mode
        assert real_camera.trigger_mode == mode

        trigger_source_options = real_camera.trigger_source.options
        for source in trigger_source_options:
            assert isinstance(source, TriggerSource)
            real_camera.trigger_source = source
            assert real_camera.trigger_source == source

            trigger_polarity_options = real_camera.trigger_polarity.options
            for polarity in trigger_polarity_options:
                assert isinstance(polarity, TriggerPolarity)
                real_camera.trigger_polarity = polarity
                assert real_camera.trigger_polarity == polarity

    real_camera.trigger_mode = original_trigger_mode
    real_camera.trigger_source = original_trigger_source
    real_camera.trigger_polarity = original_trigger_polarity


def test_frame_time(real_camera):
    frame_time = real_camera.frame_time_ms
    assert frame_time > 0
    assert (
        frame_time == (real_camera.line_interval_us * real_camera.roi_height_px / 1000) + real_camera.exposure_time_ms
    )


def test_line_interval(real_camera):
    line_interval = real_camera.line_interval_us
    assert line_interval > 0


def test_log_metadata(real_camera):
    real_camera.log_metadata()
    # This test doesn't assert anything, but it ensures the method runs without errors


# def test_acquisition(real_camera):
#     real_camera.prepare()
#     real_camera.start()
#
#     time.sleep(1)  # Allow some time for frames to be captured
#
#     frame = real_camera.grab_frame()
#     assert frame is not None
#     assert isinstance(frame, np.ndarray)
#     assert frame.shape == (real_camera.roi_height_px, real_camera.roi_width_px)
#
#     state = real_camera.acquisition_state
#     assert state.frame_index > 0
#     assert state.frame_rate_fps > 0
#
#     real_camera.stop()


if __name__ == "__main__":
    pytest.main([__file__])
