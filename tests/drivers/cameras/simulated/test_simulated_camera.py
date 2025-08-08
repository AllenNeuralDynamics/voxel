import pytest

from voxel.instrument.drivers.camera.simulated import (
    SimulatedCamera,
    MIN_WIDTH_PX,
    STEP_WIDTH_PX,
    MIN_HEIGHT_PX,
    STEP_HEIGHT_PX,
    MIN_EXPOSURE_TIME_MS,
    MAX_EXPOSURE_TIME_MS,
    SimulatedCameraSettings as Settings,
)

CAMERA_ID = "camera-1"
CAMERA_SN = "1234567890"


@pytest.fixture
def simulated_camera():
    camera = SimulatedCamera(name=CAMERA_ID, serial_number=CAMERA_SN)
    yield camera
    camera.close()


def test_camera_init(simulated_camera):
    assert simulated_camera.name == CAMERA_ID
    assert simulated_camera.serial_number == CAMERA_SN
    assert simulated_camera.roi_width_offset_px == 0
    assert simulated_camera.roi_height_offset_px == 0


""" Test Image Size Properties ______________________________________________________________________________________"""


def test_sensor_size(simulated_camera):
    assert simulated_camera.sensor_width_px > 0
    assert simulated_camera.sensor_height_px > 0


def test_roi_width_px(simulated_camera):
    def _calculate_width_offset(width_px):
        return round((simulated_camera.sensor_width_px // 2 - width_px // 2) / STEP_WIDTH_PX) * STEP_WIDTH_PX

    assert simulated_camera.roi_width_px == simulated_camera.sensor_width_px
    assert simulated_camera.roi_width_offset_px == 0

    half_width = simulated_camera.sensor_width_px // 2

    simulated_camera.roi_width_px = half_width
    assert simulated_camera.roi_width_px == half_width
    assert simulated_camera.roi_width_offset_px == _calculate_width_offset(half_width)

    simulated_camera.roi_width_px = MIN_WIDTH_PX - 1.0
    assert simulated_camera.roi_width_px == MIN_WIDTH_PX
    assert simulated_camera.roi_width_offset_px == _calculate_width_offset(MIN_WIDTH_PX)

    simulated_camera.roi_width_px = simulated_camera.sensor_width_px + 1.0
    assert simulated_camera.roi_width_px == simulated_camera.roi_width_px.maximum
    assert simulated_camera.roi_width_offset_px == 0


def test_roi_height_px(simulated_camera):
    def _calculate_height_offset(height_px):
        return round((simulated_camera.sensor_height_px // 2 - height_px // 2) / STEP_HEIGHT_PX) * STEP_HEIGHT_PX

    assert simulated_camera.roi_height_px == simulated_camera.sensor_height_px
    assert simulated_camera.roi_height_offset_px == 0

    half_height = simulated_camera.sensor_height_px // 2

    simulated_camera.roi_height_px = half_height
    assert simulated_camera.roi_height_px == half_height
    assert simulated_camera.roi_height_offset_px == _calculate_height_offset(half_height)

    simulated_camera.roi_height_px = MIN_HEIGHT_PX - 1.0
    assert simulated_camera.roi_height_px == MIN_HEIGHT_PX
    assert simulated_camera.roi_height_offset_px == _calculate_height_offset(MIN_HEIGHT_PX)

    simulated_camera.roi_height_px = simulated_camera.sensor_height_px + 1.0
    assert simulated_camera.roi_height_px == simulated_camera.roi_height_px.maximum
    assert simulated_camera.roi_height_offset_px == 0


def test_binning_and_frame_size_px(simulated_camera):
    assert simulated_camera.binning == Settings.Binning.X1
    assert simulated_camera.frame_width_px == simulated_camera.roi_width_px
    assert simulated_camera.frame_height_px == simulated_camera.roi_height_px

    simulated_camera.binning = 2
    assert simulated_camera.binning == 2
    assert simulated_camera.frame_width_px == simulated_camera.roi_width_px // 2
    assert simulated_camera.frame_height_px == simulated_camera.roi_height_px // 2

    simulated_camera.binning = Settings.Binning.X4
    assert simulated_camera.binning == 4
    assert simulated_camera.frame_width_px == simulated_camera.roi_width_px // 4
    assert simulated_camera.frame_height_px == simulated_camera.roi_height_px // 4

    simulated_camera.binning = 3
    assert simulated_camera.binning == 4


""" Test Image Format Properties ____________________________________________________________________________________"""


def test_pixel_type(simulated_camera):
    assert simulated_camera.pixel_type == Settings.PixelType.MONO8

    options = simulated_camera.pixel_type.options
    for option in options:
        simulated_camera.pixel_type = option
        assert simulated_camera.pixel_type == option

    with pytest.raises(AttributeError):
        simulated_camera.pixel_type = Settings.PixelType.MONO6


""" Test Image Acquisition Properties _______________________________________________________________________________"""


def test_exposure_time(simulated_camera):
    simulated_camera.exposure_time_ms = 20.0
    assert simulated_camera.exposure_time_ms == 20.0

    simulated_camera.exposure_time_ms = 5.0
    assert simulated_camera.exposure_time_ms == 5.0

    simulated_camera.exposure_time_ms = MIN_EXPOSURE_TIME_MS - 1.0
    assert simulated_camera.exposure_time_ms == MIN_EXPOSURE_TIME_MS

    simulated_camera.exposure_time_ms = MAX_EXPOSURE_TIME_MS + 1.0
    assert simulated_camera.exposure_time_ms == MAX_EXPOSURE_TIME_MS


def test_log_metadata(simulated_camera):
    simulated_camera.log_metadata()
    # Make sure that the function does not raise any errors


"""

def test_trigger(simulated_camera):
    assert simulated_camera.trigger == {
        "mode": "on",
        "source": "internal",
        "polarity": "rising",
    }

    simulated_camera.trigger = {
        "mode": "off",
        "source": "line0",
        "polarity": "fallingedge",
    }
    assert simulated_camera.trigger == {
        "mode": "off",
        "source": "line0",
        "polarity": "fallingedge",
    }

    with pytest.raises(ValueError):
        simulated_camera.trigger = {
            "mode": "invalid",
            "source": "line0",
            "polarity": "rising",
        }

    with pytest.raises(ValueError):
        simulated_camera.trigger = {
            "mode": "on",
            "source": "invalid",
            "polarity": "rising",
        }

    with pytest.raises(ValueError):
        simulated_camera.trigger = {
            "mode": "on",
            "source": "line0",
            "polarity": "invalid",
        }


def test_grab_frame(simulated_camera):
    frame = simulated_camera.grab_frame()
    assert frame.shape == (2048, 2048)


def test_acquisition_state(simulated_camera):
    state = simulated_camera.acquisition_state()
    assert "Frame Index" in state
    assert "Input Buffer Size" in state
    assert "Output Buffer Size" in state
    assert "Dropped Frames" in state
    assert "Data Rate [MB/s]" in state
    assert "Frame Rate [fps]" in state


"""
