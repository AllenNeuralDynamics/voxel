from unittest.mock import patch, MagicMock

import pytest

from tests.drivers.conftest import get_env
from voxel.instrument.drivers.camera.vieworks import VieworksCamera

CAMERA_1_SN = get_env("VIEWORKS_CAMERA_1_SN")
CAMERA_2_SN = get_env("VIEWORKS_CAMERA_2_SN")


@pytest.fixture
def mock_camera():
    with (
        # patch('voxel.devices.interfaces.camera.vieworks.egrabber.EGrabber') as mock_egrabber,
        # patch('voxel.devices.interfaces.camera.vieworks.vieworks_egrabber.EGenTLSingleton') as mock_gentl,
        patch("voxel.devices.interfaces.camera.vieworks.vieworks_egrabber._discover_grabber") as mock_discover
    ):
        mock_grabber = MagicMock()
        mock_egrabber_dict = {"interface": 0, "device": 0, "stream": 0}
        mock_discover.return_value = (mock_grabber, mock_egrabber_dict)
        camera = VieworksCamera(name="mock_camera", serial_number="12345")
        camera.grabber = mock_grabber
        yield camera


@pytest.fixture(scope="module")
def real_camera():
    camera = VieworksCamera(name="real_camera", serial_number=CAMERA_1_SN)
    yield camera
    camera.close()
