"""Threaded pyramid buffer — plain numpy arrays with ThreadPoolExecutor.

Best for:
- macOS development (no SharedMemory segment limits)
- Linux with TBB (numba is thread-safe with TBB threading layer)
- Simple deployments where ProcessPool overhead isn't justified
"""

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np
from vxlib.vec import UIVec3D

from ome_zarr_writer.types import Dtype, ScaleLevel

from ._base import BufferSlot, BufferStage
from ._pyramid import pyramids_3d_numba

log = logging.getLogger(__name__)


class ThreadedBufferSlot(BufferSlot):
    """Buffer slot backed by plain numpy arrays with thread-based downsampling."""

    def __init__(self, name: str, shape_l0: UIVec3D, max_level: ScaleLevel, dtype: Dtype):
        super().__init__(name, shape_l0, max_level, dtype)

        self._arrays: dict[ScaleLevel, np.ndarray] = {}
        for level in self.max_level.levels:
            shp = level.scale(self.shape_l0)
            self._arrays[level] = np.zeros((shp.z, shp.y, shp.x), dtype=self._dtype)

        self._lock = threading.Lock()
        self._stage = BufferStage.IDLE
        self._executor = ThreadPoolExecutor(max_workers=1)

    @property
    def stage(self) -> BufferStage:
        return self._stage

    def add_frame(self, frame: np.ndarray, z_idx: int) -> None:
        _, y0, x0 = self.shape_l0
        if frame.shape != (y0, x0):
            raise ValueError(f"Frame shape {frame.shape} does not match L0 frame {(y0, x0)}")
        if z_idx < 0 or z_idx >= self.shape_l0.z:
            raise IndexError(f"z_idx {z_idx} is outside L0 depth {self.shape_l0.z}")

        with self._lock:
            self._arrays[ScaleLevel.L0][z_idx, :y0, :x0] = frame.astype(self._dtype, copy=False)
            self.filled_l0 = max(self.filled_l0, z_idx + 1)

    def get_volume(self, level: ScaleLevel) -> np.ndarray:
        if level != ScaleLevel.L0 and self._stage != BufferStage.IDLE:
            raise ValueError(f"Cannot read level {level}: buffer stage is {self._stage.name}")
        return self._arrays[level]

    def start_processing(self) -> Future:
        """Submit pyramid downsampling to the thread pool."""
        self._stage = BufferStage.PROCESSING

        def _downsample():
            try:
                block = self._arrays[ScaleLevel.L0][: self.filled_l0]
                pyramid = pyramids_3d_numba(block, self.max_level, parallel=False)

                for level, vol in pyramid.items():
                    arr = self._arrays[level]
                    z = min(arr.shape[0], vol.shape[0])
                    y = min(arr.shape[1], vol.shape[1])
                    x = min(arr.shape[2], vol.shape[2])
                    arr[:z, :y, :x] = vol[:z, :y, :x].astype(self._dtype)

                self._stage = BufferStage.IDLE
            except Exception:
                log.exception("Error processing buffer %s batch %s", self.name, self.batch_idx)
                self._stage = BufferStage.ERROR
                raise

        return self._executor.submit(_downsample)

    def assign_batch(self, batch_idx: int) -> None:
        super().assign_batch(batch_idx)
        self._stage = BufferStage.COLLECTING

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        self._arrays.clear()
