"""Process-based pyramid buffer — SharedMemory with ProcessPoolExecutor.

Best for:
- Linux/macOS without TBB (numba workqueue is safe in a single-threaded worker)
- Large volumes where numba parallel speedup matters
- Avoiding the nested-threading hazard of ThreadedBufferSlot + numba

Each slot owns a long-lived worker process that attaches to shared-memory
segments by name. The main process writes L0 frames into those segments; the
worker reads them, computes the pyramid, and writes the result back into the
same segments. Only scalar metadata crosses the process boundary — no image
data is pickled.
"""

import logging
import multiprocessing as mp
import os
import threading
from concurrent.futures import Future, ProcessPoolExecutor
from multiprocessing.shared_memory import SharedMemory

import numpy as np
from vxlib.vec import UIVec3D

from ome_zarr_writer.dataset import Dtype, ScaleLevel

from ._base import BufferSlot, BufferStage
from ._pyramid import pyramids_3d_numba

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker-side state (lives inside the child process). The initializer attaches
# to the shared-memory segments once; subsequent task submissions reuse these
# views, so no per-task IPC of the image data is required.
# ---------------------------------------------------------------------------

_WORKER_SHMS: list[SharedMemory] = []
_WORKER_ARRAYS: dict[ScaleLevel, np.ndarray] = {}


def _worker_init(shm_layout: list[tuple[int, str, tuple[int, int, int]]], dtype_str: str) -> None:
    """Runs once per worker process on startup. Attaches to shared memory segments."""
    # Force the single-threaded numba layer in this worker. With one Python
    # thread per worker, workqueue is safe — no TBB needed. Defensive override
    # in case a 'tbb' value was inherited from the main process environment.
    os.environ["NUMBA_THREADING_LAYER"] = "workqueue"

    for level_value, shm_name, shape in shm_layout:
        shm = SharedMemory(name=shm_name, create=False, track=False)
        arr = np.ndarray(shape, dtype=dtype_str, buffer=shm.buf)
        _WORKER_SHMS.append(shm)
        _WORKER_ARRAYS[ScaleLevel(level_value)] = arr


def _worker_downsample(max_level_value: int, filled_l0: int) -> None:
    """Compute pyramid from the L0 view and fill the upper-level views."""
    max_level = ScaleLevel(max_level_value)
    block = _WORKER_ARRAYS[ScaleLevel.L0][:filled_l0]
    pyramid = pyramids_3d_numba(block, max_level, parallel=True)

    for level, vol in pyramid.items():
        arr = _WORKER_ARRAYS[level]
        z = min(arr.shape[0], vol.shape[0])
        y = min(arr.shape[1], vol.shape[1])
        x = min(arr.shape[2], vol.shape[2])
        arr[:z, :y, :x] = vol[:z, :y, :x].astype(arr.dtype)


# ---------------------------------------------------------------------------
# Main-process buffer
# ---------------------------------------------------------------------------


class ProcessBufferSlot(BufferSlot):
    """Buffer slot backed by SharedMemory with process-based downsampling."""

    def __init__(self, name: str, shape_l0: UIVec3D, max_level: ScaleLevel, dtype: Dtype):
        super().__init__(name, shape_l0, max_level, dtype)

        self._dtype_str = np.dtype(self._dtype).str
        self._shms: dict[ScaleLevel, SharedMemory] = {}
        self._arrays: dict[ScaleLevel, np.ndarray] = {}

        # Allocate one segment per level. Names match cleanup_shm.py's convention.
        shm_layout: list[tuple[int, str, tuple[int, int, int]]] = []
        try:
            for level in self.max_level.levels:
                shp = level.scale(self.shape_l0)
                shape = (shp.z, shp.y, shp.x)
                nbytes = int(np.prod(shape)) * self._dtype.itemsize
                shm_name = f"{self.name}_{level.value}"
                shm = SharedMemory(name=shm_name, create=True, size=nbytes, track=False)
                arr = np.ndarray(shape, dtype=self._dtype, buffer=shm.buf)
                arr.fill(0)
                self._shms[level] = shm
                self._arrays[level] = arr
                shm_layout.append((level.value, shm_name, shape))
        except Exception:
            self._release_shms()
            raise

        self._lock = threading.Lock()
        self._stage = BufferStage.IDLE

        # Force 'spawn' — the main process is multi-threaded (backend write pool),
        # and fork-after-thread is a deadlock hazard.
        ctx = mp.get_context("spawn")
        self._executor = ProcessPoolExecutor(
            max_workers=1,
            mp_context=ctx,
            initializer=_worker_init,
            initargs=(shm_layout, self._dtype_str),
        )

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
        """Submit pyramid downsampling to the worker process."""
        self._stage = BufferStage.PROCESSING
        future = self._executor.submit(
            _worker_downsample,
            self.max_level.value,
            self.filled_l0,
        )

        def _on_done(fut: Future) -> None:
            try:
                fut.result()
                self._stage = BufferStage.IDLE
            except Exception:
                log.exception("Error processing buffer %s batch %s", self.name, self.batch_idx)
                self._stage = BufferStage.ERROR

        future.add_done_callback(_on_done)
        return future

    def assign_batch(self, batch_idx: int) -> None:
        super().assign_batch(batch_idx)
        self._stage = BufferStage.COLLECTING

    def close(self) -> None:
        # Shut the worker down BEFORE unlinking segments — the worker holds
        # numpy views over the shared memory and must release them first.
        try:
            self._executor.shutdown(wait=True)
        finally:
            self._release_shms()

    def _release_shms(self) -> None:
        # Drop numpy views (which hold memoryviews into the segment) before
        # closing the underlying SharedMemory objects.
        self._arrays.clear()
        for shm in self._shms.values():
            try:
                shm.close()
            except Exception:
                log.debug("Error closing shared memory %s", shm.name, exc_info=True)
            try:
                shm.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                log.debug("Error unlinking shared memory %s", shm.name, exc_info=True)
        self._shms.clear()
