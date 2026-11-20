"""What area and line cameras share: the sensor, triggers, stream and capture states, pixel formats."""

import logging
import shutil
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from rigup.device import Device, DeviceController
from rigup.interface import StreamTier, query
from vxlib.dtype import Dtype
from vxlib.schema import FrozenModel
from vxlib.vector import IVec2D, Vec2D

from vxl.live import ValidBits
from vxl.storage import StorageSpec, StorageStatus
from vxl.system import System, remote_store_fingerprint

log = logging.getLogger(__name__)


class IntRange(BaseModel):
    """Integer range with min, max, and step."""

    min: int
    max: int
    step: int = 1


class CameraSensor(FrozenModel):
    """The size of a camera's sensor, and of 1 pixel on it."""

    pixel_um: Vec2D
    size_px: IVec2D


class TriggerMode(StrEnum):
    OFF = "off"
    ON = "on"


class TriggerPolarity(StrEnum):
    RISING_EDGE = "rising"
    FALLING_EDGE = "falling"


class StreamInfo(FrozenModel):
    frame_index: int
    input_buffer_size: int
    output_buffer_size: int
    dropped_frames: int
    frame_rate_fps: float
    data_rate_mbs: float
    payload_mbs: float | None = None


PixelFormat = Literal["MONO8", "MONO10", "MONO12", "MONO14", "MONO16"]

PIXEL_FMT_TO_DTYPE: dict[PixelFormat, Dtype] = {
    "MONO8": Dtype.UINT8,
    "MONO10": Dtype.UINT16,
    "MONO12": Dtype.UINT16,
    "MONO14": Dtype.UINT16,
    "MONO16": Dtype.UINT16,
}

PIXEL_FMT_TO_VALID_BITS: dict[PixelFormat, ValidBits] = {
    "MONO8": 8,
    "MONO10": 10,
    "MONO12": 12,
    "MONO14": 14,
    "MONO16": 16,
}

BINNING_OPTIONS = [1, 2, 4, 8]


class CaptureState(StrEnum):
    IDLE = "IDLE"
    COLLECTING = "COLLECTING"
    DONE = "DONE"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class CameraMode(StrEnum):
    IDLE = "IDLE"
    PREVIEW = "PREVIEW"
    ACQUISITION = "ACQUISITION"


class Camera(Device):
    """A camera. Area and line cameras inherit from it. It holds nothing yet: what they share moves here once the
    line camera is built."""


class CameraController[D: Camera](DeviceController[D]):
    """Runs a camera on its node. Every camera has what it needs to write what it captures: its node's storage."""

    def __init__(
        self,
        device: D,
        *,
        streaming: Mapping[StreamTier, float] | None = None,
        system: System | None = None,
    ):
        super().__init__(device, streaming=streaming)
        self._system = system if system is not None else System()

    @query()
    async def check_writable(self, storage: StorageSpec) -> StorageStatus:
        """Resolve ``storage`` on this node and prove write access with a round-trip marker write.

        The acquisition preflight (before any task): raises with a clear reason if the destination
        is unreachable or not writable, so the run aborts before any stage motion or capture.
        """

        def _check() -> StorageStatus:
            dest = self._system.resolve_storage(storage)
            root = dest.target  # client-bound path for S3, plain path for local
            root.mkdir(parents=True, exist_ok=True)
            marker = root / f".voxel_write_check-{self.device.id}"
            marker.write_text(self.device.id)  # raises on missing creds / no permission / unreachable
            marker.unlink(missing_ok=True)
            free = shutil.disk_usage(root).free if isinstance(root, Path) else -1
            return StorageStatus(host=self._system.hostname(), root=str(root), free_bytes=free)

        return await self._run(_check)

    @query()
    def remote_stores(self) -> dict[str, str]:
        """Return configured object-store names and non-secret connection fingerprints for this camera's host."""
        return {name: remote_store_fingerprint(remote.connection) for name, remote in self._system.remotes.items()}


__all__ = [
    "BINNING_OPTIONS",
    "PIXEL_FMT_TO_DTYPE",
    "PIXEL_FMT_TO_VALID_BITS",
    "Camera",
    "CameraController",
    "CameraMode",
    "CameraSensor",
    "CaptureState",
    "IntRange",
    "PixelFormat",
    "StorageStatus",
    "StreamInfo",
    "TriggerMode",
    "TriggerPolarity",
]
