import math
from pathlib import Path

import pytest
from vxlib.vector import IVec2D, Vec2D, Vec3D

from vxl.devices.camera import CameraSensor
from vxl.hal_next.config import Detector
from vxl.instruments.spim.config import Config, Task
from vxl.instruments.spim.scans import AxisRun, Scan, frame_transform, plan_task
from vxl.models import AreaROI

_EXASPIM = Detector(width={"y": 1}, height={"x": -1})
_OPEN_TOP = Detector(width={"y": 1}, height={"x": 1, "z": 1})
_FILES = Path(__file__).parent / "files"


def _sensor(pixel: float, x: int, y: int) -> CameraSensor:
    return CameraSensor(pixel_um=Vec2D(x=pixel, y=pixel), size_px=IVec2D(x=x, y=y))


def _close(a: Vec3D, b: Vec3D) -> bool:
    return all(math.isclose(p, q, abs_tol=1e-6) for p, q in zip(a, b, strict=True))


def test_exaspim_frame_matches_todays_math_for_a_camera_turned_90_degrees() -> None:
    sensor, roi = _sensor(3.76, 14192, 10640), AreaROI(x=1000, y=500, w=4000, h=3000)
    frame = frame_transform(_EXASPIM, sensor, roi, binning=1, magnification=5.0)
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
    plain = frame_transform(_EXASPIM, sensor, roi, binning=1, magnification=5.0)
    binned = frame_transform(_EXASPIM, sensor, roi, binning=2, magnification=5.0)

    assert binned.shape == (1, 1500, 2000)
    for axis in ("z", "y", "x"):
        assert binned.bounds()[axis].low == pytest.approx(plain.bounds()[axis].low)
        assert binned.bounds()[axis].high == pytest.approx(plain.bounds()[axis].high)


def test_a_slanted_frame_reaches_into_the_depth_and_along_x() -> None:
    frame = frame_transform(
        _OPEN_TOP, _sensor(6.5, 2048, 2048), AreaROI(x=0, y=0, w=2048, h=2048), binning=1, magnification=16.7
    )
    half = 2048 * 6.5 / 16.7 / 2 / math.sqrt(2)
    bounds = frame.bounds()
    assert (bounds["z"].low, bounds["z"].high) == pytest.approx((-half, half))
    assert (bounds["x"].low, bounds["x"].high) == pytest.approx((-half, half))


def test_scanned_puts_runs_slowest_first() -> None:
    sensor = _sensor(3.76, 100, 80)
    frame = frame_transform(_EXASPIM, sensor, AreaROI(x=0, y=0, w=100, h=80), binning=1, magnification=5.0)
    first = Vec3D(z=30.0, y=20.0, x=10.0)
    capture = frame.scanned(first, [AxisRun("z", 30.0, 1.0, 50)])

    assert capture.shape == (50, 80, 100)
    assert _close(capture.position((49, 0, 0)), capture.position((0, 0, 0)) + Vec3D(z=49.0, y=0.0, x=0.0))
    assert _close(capture.position((0, 39.5, 49.5)), first)
    assert math.isclose(capture.bounds()["z"].length, 50.0)


def test_a_run_needs_a_free_frame_axis() -> None:
    frame = frame_transform(_EXASPIM, _sensor(1.0, 10, 10), AreaROI(x=0, y=0, w=10, h=10), binning=1, magnification=1)
    with pytest.raises(ValueError, match="free axis"):
        frame.scanned(Vec3D(z=0, y=0, x=0), [AxisRun("x", 0, 1.0, 5), AxisRun("z", 0, 1.0, 5)])


def _plan(name: str, sensor: CameraSensor, x: tuple[float, float], y: tuple[float, float], z: float) -> list[Scan]:
    """The scans of 1 task over a box, with the ``gfp`` profile of an example file."""
    config = Config.load(_FILES / name)
    region = {
        "xy": {"kind": "bounding_box", "points": [{"x": x[0], "y": y[0]}, {"x": x[1], "y": y[1]}]},
        "z": {"start": 0, "end": z},
    }
    task = Task.complete({"id": "t", "region": region, "profiles": ["gfp"]}, config.default.task)
    return plan_task(task, config.hal, config.default, dict.fromkeys(config.hal.optics.detectors(), sensor))


def test_exaspim_steps_z_and_its_side_selector_follows_x() -> None:
    sensor = _sensor(3.76, 14192, 10640)
    (left,) = _plan("exaspim-v1.yaml", sensor, (0, 30000), (0, 9000), 100)
    (right,) = _plan("exaspim-v1.yaml", sensor, (30000, 50000), (0, 9000), 100)

    assert left.runs == [AxisRun("z", 0.0, 1.0, 101)]
    assert left.transforms["camera"].shape == (101, 10640, 14192)
    assert left.positions == {"excitation_side_selector": "left", "fw_emission": "BP525"}
    assert right.positions == {"excitation_side_selector": "right", "fw_emission": "BP525"}


def test_open_top_sweeps_x() -> None:
    (scan,) = _plan("open-top.yaml", _sensor(6.5, 2048, 2048), (0, 1000), (0, 500), 200)
    assert scan.runs == [AxisRun("x", 0.0, 0.5, 2001)]
    assert scan.transforms["camera"].shape == (2001, 2048, 2048)
