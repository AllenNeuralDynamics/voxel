"""The live image: each camera's frames passed on to the screen, unopened, and what the screen reads about them."""

import asyncio
import math
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from vxlib.reactivity import Emitter
from vxlib.schema import FrozenModel
from vxlib.vector import Vec3D

from vxl.core.instrument.config import DeviceUid
from vxl.core.instrument.geometry import Transform
from vxl.devices.camera import AreaCameraHandle
from vxl.live import LiveLayer, LiveSourceEmission, LiveViewport, live_source_header
from vxl.live.protocol import StagePosition

if TYPE_CHECKING:
    from vxlib.lifecycle import Teardown

_KEPT_POSITIONS = 16
"""How many recent frames of each camera keep their stage position, for zoomed frames that come late."""


_SAME_PLANE_DEG = 1.0
"""Pictures whose planes differ by less than this share a plane: a camera mounted a little crooked still counts."""

_SAME_PLANE = math.cos(math.radians(_SAME_PLANE_DEG))

type Box = tuple[float, float, float, float]
"""A box in a plane, in µm from the stage position: left, top, width, height."""

type Point = tuple[float, float]
"""A place or a direction in a plane, in µm: how far right, then how far down."""


class Picture(FrozenModel):
    """Where 1 camera's picture sits in its plane, in µm from the stage position. The point of the picture at (s, t),
    each from 0 to 1, is at ``corner + s * width + t * height``."""

    corner: Point
    width: Point
    height: Point

    def viewport(self, box: Box) -> LiveViewport | None:
        """A box of the plane, in µm from the stage position, as this camera's own viewport: fractions of its
        picture. It is the box around the box's corners in the picture's own coordinates, cut to the picture.
        ``None`` when the box does not touch the picture."""
        (w1, w2), (h1, h2), (c1, c2) = self.width, self.height, self.corner
        det = w1 * h2 - w2 * h1
        left, top, width, height = box
        s_values, t_values = [], []
        for x, y in ((left, top), (left + width, top), (left, top + height), (left + width, top + height)):
            dx, dy = x - c1, y - c2
            s_values.append((dx * h2 - dy * h1) / det)
            t_values.append((w1 * dy - w2 * dx) / det)
        s0, s1 = max(0.0, min(s_values)), min(1.0, max(s_values))
        t0, t1 = max(0.0, min(t_values)), min(1.0, max(t_values))
        if s1 <= s0 or t1 <= t0:
            return None
        return LiveViewport(x=s0, y=t0, w=s1 - s0, h=t1 - t0)


class Plane(FrozenModel):
    """The pictures that lie in 1 plane of the specimen. ``right`` and ``down`` are the plane's 2 screen directions, as
    unit vectors in the specimen's axes."""

    right: Vec3D
    down: Vec3D
    pictures: dict[DeviceUid, Picture]


def planes_of(frames: Mapping[DeviceUid, Transform]) -> tuple[Plane, ...]:
    """The planes of some cameras' frames at stage position 0, each with the pictures that lie in it."""
    planes: list[Plane] = []
    for normal, members in _same_plane_groups(frames):
        right, down = _screen_axes(normal)
        pictures = {camera: _picture(frame, right, down) for camera, frame in members.items()}
        planes.append(Plane(right=_rounded(right), down=_rounded(down), pictures=pictures))
    return tuple(planes)


def _normal(frame: Transform) -> Vec3D:
    """The unit vector across a frame's picture."""
    across = frame.steps[2].cross(frame.steps[1])
    return across / across.length()


def _same_plane_groups(frames: Mapping[DeviceUid, Transform]) -> list[tuple[Vec3D, dict[DeviceUid, Transform]]]:
    """The frames grouped by the plane they lie in: a frame joins the first group whose plane is within
    ``_SAME_PLANE_DEG`` of its own."""
    groups: list[tuple[Vec3D, dict[DeviceUid, Transform]]] = []
    for camera, frame in frames.items():
        normal = _normal(frame)
        group = next((members for known, members in groups if abs(normal.dot(known)) > _SAME_PLANE), None)
        if group is None:
            groups.append((normal, {camera: frame}))
        else:
            group[camera] = frame
    return groups


def _screen_axes(normal: Vec3D) -> tuple[Vec3D, Vec3D]:
    """A plane's screen directions. The plane follows the stage: of the 2 stage axes that lie most in it, the first of
    x, y, z points right and the other down."""
    stage = [Vec3D(x=1.0, y=0.0, z=0.0), Vec3D(x=0.0, y=1.0, z=0.0), Vec3D(x=0.0, y=0.0, z=1.0)]
    flat = [axis - normal * axis.dot(normal) for axis in stage]
    first, second = sorted(sorted(range(3), key=lambda i: -round(flat[i].length(), 6))[:2])
    right = flat[first] / flat[first].length()
    down = flat[second] - right * flat[second].dot(right)
    return right, down / down.length()


def _picture(frame: Transform, right: Vec3D, down: Vec3D) -> Picture:
    """Where a frame's picture sits in a plane: its corner and its 2 edges, on the plane's screen directions."""
    _, rows, columns = frame.shape
    x_step, y_step = frame.steps[2], frame.steps[1]
    corner = frame.origin - x_step / 2 - y_step / 2

    def on(vector: Vec3D) -> Point:
        return round(vector.dot(right), 3), round(vector.dot(down), 3)

    return Picture(corner=on(corner), width=on(x_step * columns), height=on(y_step * rows))


def _rounded(vector: Vec3D) -> Vec3D:
    return Vec3D(x=round(vector.x, 6), y=round(vector.y, 6), z=round(vector.z, 6))


class LiveView(FrozenModel):
    """The live image as a screen sees it: where each camera's picture sits, by plane. A new ``stream_revision``
    means older frames are no longer valid."""

    stream_revision: int = 0
    planes: tuple[Plane, ...] = ()


class LiveRelay:
    """Passes each camera's live frames on, without opening them. It reads only a frame's header: a frame of an old
    stream is dropped, and each new frame gets the stage position from when it first came. It sends each frame it
    passes on to ``frames``: its camera, layer, packed bytes, and that position. Later frames with the same number,
    such as a zoom of a stopped image, get that same position.

    It listens from :meth:`start` to :meth:`stop`, so a zoom of a stopped image still comes through. :meth:`reset`
    starts a new stream on cameras; a camera without a stream from it has nothing passed on."""

    def __init__(
        self,
        cameras: Mapping[DeviceUid, AreaCameraHandle],
        stage: Callable[[], StagePosition | None],
        frames: Emitter[LiveSourceEmission],
    ) -> None:
        self._cameras = cameras
        self._stage = stage
        self._frames = frames
        self._streams: dict[DeviceUid, str] = {}
        self._positions: dict[DeviceUid, dict[int, StagePosition | None]] = {}
        self._teardowns: list[Teardown] = []
        self._resetting = asyncio.Lock()

    @property
    def streaming(self) -> tuple[DeviceUid, ...]:
        """The cameras that have a stream from the last :meth:`reset`."""
        return tuple(self._streams)

    def start(self) -> None:
        """Listen to every camera's live topics."""
        for uid, camera in self._cameras.items():
            for topic, layer in (("live", LiveLayer.OVERVIEW), ("live_viewport", LiveLayer.VIEWPORT)):
                self._teardowns.append(camera.subscribe(topic, self._forward(uid, layer)))

    def stop(self) -> None:
        """Stop listening, and forget every stream."""
        for teardown in self._teardowns:
            teardown()
        self._teardowns.clear()
        self._streams.clear()
        self._positions.clear()

    async def reset(self, cameras: Mapping[DeviceUid, AreaCameraHandle]) -> None:
        """Start a new stream on each of ``cameras``, and drop every other stream with its positions. 1 reset runs at
        a time, so the streams kept are always those of the last reset to run."""
        async with self._resetting:
            self._streams.clear()
            self._positions.clear()
            ids = await asyncio.gather(*(camera.reset_live_stream() for camera in cameras.values()))
            self._streams = dict(zip(cameras, ids, strict=True))

    def _forward(self, uid: DeviceUid, layer: LiveLayer) -> Callable[[bytes], Any]:
        async def forward(frame: bytes) -> None:
            try:
                header = live_source_header(frame)
            except ValueError:
                return  # not a live frame; the camera logs its own errors
            if header.camera_id != uid or header.source_stream_id != self._streams.get(uid):
                return
            await self._frames.emit((uid, layer, frame, self._position(uid, header.frame_idx)))

        return forward

    def _position(self, uid: DeviceUid, frame_idx: int) -> StagePosition | None:
        """The stage position of a frame: read when its number is new, kept for the latest frames."""
        positions = self._positions.setdefault(uid, {})
        if frame_idx > max(positions, default=-1):
            positions[frame_idx] = self._stage()
            if len(positions) > _KEPT_POSITIONS:
                del positions[min(positions)]
        return positions.get(frame_idx)


__all__ = ["Box", "LiveRelay", "LiveView", "Picture", "Plane", "planes_of"]
