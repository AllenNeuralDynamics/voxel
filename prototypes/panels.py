"""The panels of a preview: the cameras that see 1 plane of the sample, with each camera's picture placed in that
plane. A screen can draw the pictures, a scale bar and the stage axes from it, and say where in the sample the mouse
is. The instrument can turn a viewport of a panel into each camera's own viewport.

Run from the repo root: ``uv run -m prototypes.panels``. It prints the panels of the example rigs of the tests."""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
from vxl_instruments.spim.plan import _light
from vxlib.vector import IVec2D, Transform, Vec2D, Vec3D

from instruments.tests.spim.support import load_file
from vxl.devices.camera import AreaROI, CameraSensor
from vxl.station.instrument.config import Detector
from vxl.station.instrument.geometry import camera_frame

_FILES = Path("instruments/src/vxl_instruments/spim/templates")
_SAME_PLANE_DEG = 1.0

type Point = tuple[float, float]
"""A place or a direction in a panel, in µm: how far right, then how far down."""

type Rect = tuple[float, float, float, float]
"""Left, top, width, height."""


@dataclass(frozen=True)
class Picture:
    """Where 1 camera's picture sits in its panel, in µm from the stage position. The point of the picture at
    (s, t), each from 0 to 1, is at ``corner + s * width + t * height``."""

    corner: Point
    width: Point
    height: Point

    def viewport(self, rect: Rect) -> Rect:
        """A rectangle of the panel, in µm from the stage position, as this camera's own viewport: fractions of
        its picture. It is the box around the turned corners, cut to the picture."""
        left, top, w, h = rect
        to_panel = np.column_stack([self.width, self.height])
        corners = [
            np.linalg.solve(to_panel, np.array(corner) - np.array(self.corner))
            for corner in product((left, left + w), (top, top + h))
        ]
        low = np.clip(np.min(corners, axis=0), 0, 1)
        size = np.clip(np.max(corners, axis=0), 0, 1) - low
        return (float(low[0]), float(low[1]), float(size[0]), float(size[1]))


@dataclass(frozen=True)
class Panel:
    """The cameras that see 1 plane of the sample. ``right`` and ``down`` are the 2 screen directions of the panel,
    as directions of length 1 in the sample."""

    right: Vec3D
    down: Vec3D
    pictures: dict[str, Picture]

    def sample_position(self, point: Point, stage: Vec3D) -> Vec3D:
        """The place in the sample under a point of the panel, with the stage at ``stage``."""
        return stage + self.right * point[0] + self.down * point[1]

    def stage_axes(self) -> dict[str, tuple[float, float, float]]:
        """How far each stage axis points right, down, and away from the viewer: what a small drawing of the axes
        in a corner of the panel shows."""
        right, down = _array(self.right), _array(self.down)
        away = np.cross(right, down)
        return {
            name: (float(axis @ right), float(axis @ down), float(axis @ away))
            for name, axis in zip("xyz", np.eye(3), strict=True)
        }


def panels(frames: Mapping[str, Transform]) -> list[Panel]:
    """The panels of some cameras. ``frames`` gives each camera's frame in the sample at stage position 0. Cameras
    share a panel when their frames lie in the same plane. A panel follows the stage: of the 2 stage axes that lie
    most in its plane, the first in the order x, y, z points right and the other points down."""
    planes: list[tuple[np.ndarray, dict[str, Transform]]] = []
    for camera, frame in frames.items():
        normal = np.cross(_array(frame.steps[2]), _array(frame.steps[1]))
        normal = normal / np.linalg.norm(normal)
        for known, members in planes:
            if abs(normal @ known) > np.cos(np.radians(_SAME_PLANE_DEG)):
                members[camera] = frame
                break
        else:
            planes.append((normal, {camera: frame}))
    found: list[Panel] = []
    for normal, members in planes:
        flat = [axis - (axis @ normal) * normal for axis in np.eye(3)]
        most = sorted(range(3), key=lambda i: -round(float(np.linalg.norm(flat[i])), 6))[:2]
        first, second = sorted(most)
        right = flat[first] / np.linalg.norm(flat[first])
        down = flat[second] - (flat[second] @ right) * right
        down = down / np.linalg.norm(down)
        pictures: dict[str, Picture] = {}
        for camera, frame in members.items():
            _, rows, columns = frame.shape
            x_step, y_step = _array(frame.steps[2]), _array(frame.steps[1])
            corner = _array(frame.origin) - x_step / 2 - y_step / 2
            placed = [(float(v @ right), float(v @ down)) for v in (corner, x_step * columns, y_step * rows)]
            pictures[camera] = Picture(*placed)
        found.append(Panel(_vec(right), _vec(down), pictures))
    return found


def _axes(detector: Detector, magnification: float) -> tuple[Vec3D, Vec3D]:
    width, height = detector.sides()
    return width / magnification, height / magnification


def _array(vector: Vec3D) -> np.ndarray:
    return np.array([vector.x, vector.y, vector.z])


def _vec(array: np.ndarray) -> Vec3D:
    return Vec3D(x=float(array[0]), y=float(array[1]), z=float(array[2]))


def _show(title: str, frames: Mapping[str, Transform], rect: Rect, point: Point) -> None:
    stage = Vec3D(x=12000.0, y=5000.0, z=300.0)
    print(f"\n{title}")
    for panel in panels(frames):
        print(f"  panel: right {_rounded(panel.right)}, down {_rounded(panel.down)}")
        for camera, picture in panel.pictures.items():
            width, height = (tuple(round(v, 1) for v in side) for side in (picture.width, picture.height))
            print(f"    {camera}: width {width} µm, height {height} µm")
        axes = {name: tuple(round(v, 2) + 0.0 for v in parts) for name, parts in panel.stage_axes().items()}
        print(f"    the stage axes on the screen (right, down, away): {axes}")
        for camera, picture in panel.pictures.items():
            viewport = tuple(round(v, 3) + 0.0 for v in picture.viewport(rect))
            print(f"    viewport {rect} µm -> {camera} gets {viewport}")
        under = _rounded(panel.sample_position(point, stage))
        print(f"    the mouse at {point} µm, the stage at {_rounded(stage)} -> sample {under}")


def _rounded(vector: Vec3D) -> tuple[float, float, float]:
    return (round(vector.x, 2) + 0.0, round(vector.y, 2) + 0.0, round(vector.z, 2) + 0.0)


def main() -> None:
    exaspim = load_file(_FILES / "z-step.yaml")
    sensors = {"camera": CameraSensor(pixel_um=Vec2D(x=3.76, y=3.76), size_px=IVec2D(x=14192, y=10640))}
    picks = {"excitation_side_selector": "left"}
    _, frames = _light(exaspim.config, exaspim.default.profiles["gfp"], picks, sensors)
    _show("exaSPIM, from exaspim-v1.yaml", frames, rect=(0.0, -1500.0, 2000.0, 1500.0), point=(1000.0, -500.0))

    open_top = load_file(_FILES / "x-sweep-oblique.yaml")
    sensors = {"camera": CameraSensor(pixel_um=Vec2D(x=6.5, y=6.5), size_px=IVec2D(x=2048, y=2048))}
    _, frames = _light(open_top.config, open_top.default.profiles["gfp"], {}, sensors)
    title = "open-top, tilted 45°, from x-sweep-oblique.yaml"
    _show(title, frames, rect=(0.0, -200.0, 200.0, 200.0), point=(200.0, 0.0))

    big = CameraSensor(pixel_um=Vec2D(x=6.5, y=6.5), size_px=IVec2D(x=2048, y=2048))
    small = CameraSensor(pixel_um=Vec2D(x=6.5, y=6.5), size_px=IVec2D(x=1024, y=1024))
    frames = {
        "camera_1": camera_frame(
            _axes(Detector(width={"x": 1}, height={"y": 1}), 10),
            big,
            AreaROI(x=0, y=0, w=2048, h=2048),
        ),
        "camera_2": camera_frame(
            _axes(Detector(width={"x": -1}, height={"y": 1}), 10),
            small,
            AreaROI(x=0, y=0, w=1024, h=1024),
        ),
    }
    _show(
        "made up: 2 cameras behind a splitter, the second mirrored and with a smaller sensor",
        frames,
        rect=(0.0, -300.0, 300.0, 300.0),
        point=(100.0, 100.0),
    )


if __name__ == "__main__":
    main()
