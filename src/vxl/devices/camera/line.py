"""A line camera: the device that reads out 1 row of its sensor at a time."""

from vxl.devices.base import DeviceType
from vxl.devices.camera.base import Camera, CameraController
from vxl.devices.camera.handle import CameraHandle


class LineCamera(Camera, kind=DeviceType.LINE_CAMERA, controller=CameraController):
    """A line camera. Not built yet: it answers only the storage queries that every camera has, and no driver builds
    on it."""


class LineCameraHandle(CameraHandle[LineCamera]):
    """A line camera's handle. Not built yet: only what every camera's handle has."""


__all__ = ["LineCamera", "LineCameraHandle"]
