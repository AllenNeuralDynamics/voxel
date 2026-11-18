import math

import pytest
from vxlib.vector import IVec2D, Vec2D, Vec3D

from vxl.core.instrument.config import Detector
from vxl.core.instrument.geometry import AxisRun, Transform
from vxl.devices.camera import AreaROI, CameraSensor

_EXASPIM = Detector(width={"y": 1}, height={"x": -1})
_OPEN_TOP = Detector(width={"y": 1}, height={"x": 1, "z": 1})


def _axes(detector: Detector, magnification: float) -> tuple[Vec3D, Vec3D]:
    """Where 1 µm along the sensor lands in the specimen, behind ``magnification``."""
    width, height = detector.sides()
    return width / magnification, height / magnification


def _sensor(pixel: float, x: int, y: int) -> CameraSensor:
    return CameraSensor(pixel_um=Vec2D(x=pixel, y=pixel), size_px=IVec2D(x=x, y=y))


def _close(a: Vec3D, b: Vec3D) -> bool:
    return all(math.isclose(p, q, abs_tol=1e-6) for p, q in zip(a, b, strict=True))


def test_exaspim_frame_matches_todays_math_for_a_camera_turned_90_degrees() -> None:
    sensor, roi = _sensor(3.76, 14192, 10640), AreaROI(x=1000, y=500, w=4000, h=3000)
    frame = Transform.frame(_axes(_EXASPIM, 5.0), sensor, roi, binning=1)
    bounds = frame.bounds()

    # Today's _compute_profile_fovs with rotation_deg 90: center (-cy, cx), size (height, width).
    factor = 3.76 / 5.0
    cx = (roi.x + roi.w / 2 - 14192 / 2) * factor
    cy = (roi.y + roi.h / 2 - 10640 / 2) * factor
    assert frame.shape == (1, 3000, 4000)
    assert (bounds["y"].middle, bounds["x"].middle) == (pytest.approx(cx), pytest.approx(-cy))
    assert (bounds["y"].length, bounds["x"].length) == (pytest.approx(4000 * factor), pytest.approx(3000 * factor))


def test_binning_keeps_the_area_and_joins_pixels() -> None:
    sensor, roi = _sensor(3.76, 14192, 10640), AreaROI(x=1000, y=500, w=4000, h=3000)
    plain = Transform.frame(_axes(_EXASPIM, 5.0), sensor, roi, binning=1)
    binned = Transform.frame(_axes(_EXASPIM, 5.0), sensor, roi, binning=2)

    assert binned.shape == (1, 1500, 2000)
    for axis in ("z", "y", "x"):
        assert binned.bounds()[axis].low == pytest.approx(plain.bounds()[axis].low)
        assert binned.bounds()[axis].high == pytest.approx(plain.bounds()[axis].high)


def test_a_slanted_frame_reaches_into_the_depth_and_along_x() -> None:
    frame = Transform.frame(
        _axes(_OPEN_TOP, 16.7), _sensor(6.5, 2048, 2048), AreaROI(x=0, y=0, w=2048, h=2048), binning=1
    )
    half = 2048 * 6.5 / 16.7 / 2 / math.sqrt(2)
    bounds = frame.bounds()
    assert (bounds["z"].low, bounds["z"].high) == pytest.approx((-half, half))
    assert (bounds["x"].low, bounds["x"].high) == pytest.approx((-half, half))


def test_a_run_puts_the_scan_on_array_axis_0() -> None:
    sensor = _sensor(3.76, 100, 80)
    frame = Transform.frame(_axes(_EXASPIM, 5.0), sensor, AreaROI(x=0, y=0, w=100, h=80), binning=1)
    first = Vec3D(z=30.0, y=20.0, x=10.0)
    capture = AxisRun("z", 30.0, 1.0, 50).transform(frame, first)

    assert capture.shape == (50, 80, 100)
    assert _close(capture.position((49, 0, 0)), capture.position((0, 0, 0)) + Vec3D(z=49.0, y=0.0, x=0.0))
    assert _close(capture.position((0, 39.5, 49.5)), first)
    assert math.isclose(capture.bounds()["z"].length, 50.0)


def test_a_scan_needs_a_free_frame_axis() -> None:
    frame = Transform.frame(_axes(_EXASPIM, 1), _sensor(1.0, 10, 10), AreaROI(x=0, y=0, w=10, h=10), binning=1)
    capture = AxisRun("x", 0, 1.0, 5).transform(frame, Vec3D(z=0, y=0, x=0))
    with pytest.raises(ValueError, match="free axis"):
        AxisRun("z", 0, 1.0, 5).transform(capture, Vec3D(z=0, y=0, x=0))
