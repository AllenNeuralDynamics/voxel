from unittest.mock import call

from voxel.instrument.drivers.camera import GenTLException


def test_camera_initialization(mock_camera):
    assert mock_camera.name == "mock_camera"
    assert mock_camera.serial_number == "12345"


def test_query_binning_lut(mock_camera):
    def mock_get(param, dtype=None):
        if param == "BinningHorizontal":
            return "X1"
        elif param == "@ee BinningHorizontal" and dtype == list:
            return ["X1", "X2", "X3", "X4", "X8"]
        raise ValueError(f"Unexpected get call with param: {param}, dtype: {dtype}")

    def mock_set(param, value):
        if param == "BinningHorizontal" and value == "X8":
            raise GenTLException("Unsupported binning option: X8", ValueError)

    mock_camera.grabber.remote.get.side_effect = mock_get
    mock_camera.grabber.remote.set.side_effect = mock_set

    binning_lut = mock_camera._get_binning_lut()

    assert binning_lut == {1: "X1", 2: "X2", 4: "X4"}

    mock_camera.grabber.remote.set.assert_has_calls(
        [
            call("BinningHorizontal", "X1"),
            call("BinningHorizontal", "X2"),
            call("BinningHorizontal", "X3"),
            call("BinningHorizontal", "X4"),
            call("BinningHorizontal", "X8"),
            call("BinningHorizontal", "X1"),  # Restoration
        ]
    )


def test_query_delimination_prop(mock_camera):
    # Setup mock responses
    mock_camera.grabber.remote.get.side_effect = [
        100,  # Width.Min
        1000,  # Width.Max
        2,  # Width.Inc
        50,  # Height.Min
        500,  # Height.Max
        2,  # Height.Inc
        0.1,  # ExposureTime.Min
        1000,  # ExposureTime.Max
        0.1,  # ExposureTime.Inc
    ]

    # Test Width delimination
    assert mock_camera._get_delimination_prop("Width", "Min") == 100
    assert mock_camera._get_delimination_prop("Width", "Max") == 1000
    assert mock_camera._get_delimination_prop("Width", "Inc") == 2

    # Test Height delimination
    assert mock_camera._get_delimination_prop("Height", "Min") == 50
    assert mock_camera._get_delimination_prop("Height", "Max") == 500
    assert mock_camera._get_delimination_prop("Height", "Inc") == 2

    # Test ExposureTime delimination
    assert mock_camera._get_delimination_prop("ExposureTime", "Min") == 0.1
    assert mock_camera._get_delimination_prop("ExposureTime", "Max") == 1000
    assert mock_camera._get_delimination_prop("ExposureTime", "Inc") == 0.1

    # Verify that the correct calls were made
    expected_calls = [
        call("Width.Min"),
        call("Width.Max"),
        call("Width.Inc"),
        call("Height.Min"),
        call("Height.Max"),
        call("Height.Inc"),
        call("ExposureTime.Min"),
        call("ExposureTime.Max"),
        call("ExposureTime.Inc"),
    ]
    mock_camera.grabber.remote.get.assert_has_calls(expected_calls)

    # Test caching behavior
    mock_camera.grabber.remote.get.reset_mock()

    # These calls should use cached values and not call the grabber again
    assert mock_camera._get_delimination_prop("Width", "Min") == 100
    assert mock_camera._get_delimination_prop("Height", "Max") == 500
    assert mock_camera._get_delimination_prop("ExposureTime", "Inc") == 0.1

    mock_camera.grabber.remote.get.assert_not_called()


def test_invalidate_delimination_prop(mock_camera):
    # Setup initial values
    mock_camera._delimination_props = {
        "Width": {"Min": 100, "Max": 1000, "Inc": 2},
        "Height": {"Min": 50, "Max": 500, "Inc": 2},
        "ExposureTime": {"Min": 0.1, "Max": 1000, "Inc": 0.1},
    }

    # Invalidate Width delimination
    mock_camera._invalidate_delimination_prop("Width")

    assert mock_camera._delimination_props["Width"] == {"Min": None, "Max": None, "Inc": None}
    assert mock_camera._delimination_props["Height"] == {"Min": 50, "Max": 500, "Inc": 2}
    assert mock_camera._delimination_props["ExposureTime"] == {"Min": 0.1, "Max": 1000, "Inc": 0.1}


def test_invalidate_all_delimination_props(mock_camera):
    # Setup initial values
    mock_camera._delimination_props = {
        "Width": {"Min": 100, "Max": 1000, "Inc": 2},
        "Height": {"Min": 50, "Max": 500, "Inc": 2},
        "ExposureTime": {"Min": 0.1, "Max": 1000, "Inc": 0.1},
    }

    # Invalidate all delimination props
    mock_camera._invalidate_all_delimination_props()

    for prop in mock_camera._delimination_props.values():
        assert prop == {"Min": None, "Max": None, "Inc": None}
