import math

import pytest
from vxlib.vector import IVec2D, Transform, Vec2D, Vec3D

from vxl.devices.camera import AreaROI, CameraSensor
from vxl.instrument.config import Detector
from vxl.instrument.geometry import camera_frame
from vxl.instrument.live import Picture, planes_of

_SENSOR = CameraSensor(pixel_um=Vec2D(x=1.0, y=1.0), size_px=IVec2D(x=1000, y=800))
_FULL = AreaROI(x=0, y=0, w=1000, h=800)


def _frame(width: dict[str, float], height: dict[str, float]) -> Transform:
    """A camera's frame with its sensor's sides along ``width`` and ``height``, at magnification 1."""
    return camera_frame(Detector.model_validate({"width": width, "height": height}).sides(), _SENSOR, _FULL)


def test_a_flat_camera_lies_in_the_stage_plane_x_right_and_y_down() -> None:
    (plane,) = planes_of({"camera": _frame({"x": 1}, {"y": 1})})
    assert (plane.right, plane.down) == (Vec3D(x=1.0, y=0.0, z=0.0), Vec3D(x=0.0, y=1.0, z=0.0))
    assert plane.pictures["camera"] == Picture(corner=(-500.0, -400.0), width=(1000.0, 0.0), height=(0.0, 800.0))


def test_cameras_behind_a_splitter_share_a_plane_and_a_mirrored_one_runs_the_other_way() -> None:
    (plane,) = planes_of({"a": _frame({"x": 1}, {"y": 1}), "b": _frame({"x": -1}, {"y": 1})})
    assert (plane.pictures["a"].width, plane.pictures["b"].width) == ((1000.0, 0.0), (-1000.0, 0.0))


def test_cameras_that_see_different_planes_get_a_plane_each() -> None:
    planes = planes_of({"top": _frame({"x": 1}, {"y": 1}), "side": _frame({"y": 1}, {"z": 1})})
    assert [set(plane.pictures) for plane in planes] == [{"top"}, {"side"}]


def test_a_tilted_camera_s_plane_mixes_x_and_z() -> None:
    (plane,) = planes_of({"camera": _frame({"y": 1}, {"x": 1, "z": 1})})
    half = round(1 / math.sqrt(2), 6)
    assert (plane.right, plane.down) == (Vec3D(x=half, y=0.0, z=half), Vec3D(x=0.0, y=1.0, z=0.0))


def test_a_box_becomes_each_camera_s_own_part_of_its_picture() -> None:
    picture = Picture(corner=(-500.0, -400.0), width=(1000.0, 0.0), height=(0.0, 800.0))
    viewport = picture.viewport((-100.0, -80.0, 200.0, 160.0))
    assert viewport is not None
    assert (viewport.x, viewport.y, viewport.w, viewport.h) == pytest.approx((0.4, 0.4, 0.2, 0.2))
    assert picture.viewport((600.0, 0.0, 100.0, 100.0)) is None  # outside the picture
