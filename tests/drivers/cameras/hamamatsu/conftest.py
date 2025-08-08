from unittest.mock import patch, MagicMock

import pytest

from voxel.instrument.drivers import HamamatsuCamera

HAMAMATSU_SERIAL_NUMBER = "302482"
HAMAMATSU_CAMERA_ID = "test_hamamatsu_camera"


@pytest.fixture
def real_camera():
    camera = HamamatsuCamera(name=HAMAMATSU_CAMERA_ID, serial_number=HAMAMATSU_SERIAL_NUMBER)
    yield camera
    camera.close()


@pytest.fixture
def mock_camera():
    with patch("voxel.devices.interfaces.camera.hamamatsu.hamamatsu_dcam.discover_dcam") as mock_discover:
        mock_dcam = MagicMock()
        mock_discover.return_value = (mock_dcam, 1)
        camera = HamamatsuCamera(name=HAMAMATSU_CAMERA_ID, serial_number=HAMAMATSU_SERIAL_NUMBER)
        yield camera
