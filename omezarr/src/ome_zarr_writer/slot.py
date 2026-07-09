"""Process-based buffer slot that downsamples AND writes — the whole batch pipeline in one worker.

`BatchSlot`'s worker does both halves of the batch pipeline: it reads the collected L0 frames from
shared memory, builds the pyramid, and writes every level to the store itself. The main process only
fills L0 (`add_frame`) and waits on the result — so the CPU/GIL-heavy compress+write never touches the
capture event loop. That's the whole point: overlap the flush with capture without starving it.

Self-contained by design: there is no `get_volume` (the main process never reads the pyramid) and no
separate flush stage — downsample and write are one worker task.

    slot = BatchSlot(name="s0", shape_l0=..., max_level=ScaleLevel.L7, dtype=Dtype.UINT16)
    slot.bind_output(setup)              # once per dataset: worker opens one ArrayWriter per level
    slot.assign_batch(0)                 # IDLE → COLLECTING
    for z, frame in enumerate(frames):
        slot.add_frame(frame, z)
    fut = slot.flush()                   # worker: downsample + write this batch to the store (async)
    result = fut.result()                # BatchResult(process/flush start+end timestamps, flushed_bytes)
    ...
    slot.close()                         # close writers, shut the worker, unlink shared memory
"""

import logging
import math
import multiprocessing as mp
import os
import signal
import threading
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path

import numpy as np
from cloudpathlib import S3Path
from pydantic import BaseModel, ConfigDict
from vxlib.vec import UIVec3D

from ome_zarr_writer.array import ArrayWriter
from ome_zarr_writer.dataset import Dtype, ScaleLevel
from ome_zarr_writer.storage import S3Store

from .pyramid import pyramids_3d_numba

log = logging.getLogger(__name__)

# Threads used to prefault (commit) a large segment at allocation; numpy's fill releases the GIL, so
# leading-axis slices commit in parallel. Segments below the threshold are filled in one call.
_PREFAULT_WORKERS = min(32, os.cpu_count() or 1)
_PREFAULT_MIN_BYTES = 1 << 28  # 256 MiB


def _prefault_zero(arr: np.ndarray) -> None:
    """Zero (and thereby commit) a freshly created SharedMemory-backed array, in parallel — so the
    commit is paid here, off the capture path, rather than as page faults during add_frame."""
    n = int(arr.shape[0])
    if arr.nbytes < _PREFAULT_MIN_BYTES or n <= 1 or _PREFAULT_WORKERS <= 1:
        arr.fill(0)
        return
    workers = min(_PREFAULT_WORKERS, n)
    step = math.ceil(n / workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda z: arr[z : z + step].fill(0), range(0, n, step)))


class SlotStage(IntEnum):
    """Lifecycle of a `BatchSlot`. IDLE is the only reusable stage (the buffer is empty).

    IDLE → COLLECTING → PROCESSING → IDLE   (PROCESSING covers both downsample and write, in the worker)
                                   → ERROR   (worker task failed; terminal)
    """

    ERROR = -1
    IDLE = 0
    COLLECTING = 1
    PROCESSING = 2


class OutputSetup(BaseModel):
    """Backend-agnostic, picklable description of where and how a slot's worker writes its pyramid.

    Built once per dataset by the writer and handed to the slot (`bind_output`); it crosses the spawn
    boundary to the worker, which instantiates ``backend`` and opens one ArrayWriter per level under
    ``author_root``. Carries no live handles. For `Local`/`StagedS3` the worker writes to a local
    ``author_root`` (scratch when staging) with ``store=None``; only `DirectS3` passes an ``S3Path`` +
    ``S3Store`` for a direct remote write.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)  # S3Path / S3Store aren't pydantic types

    backend: ArrayWriter.Backend  # which ArrayWriter the worker instantiates (TS, zarrs, …)
    author_root: Path | S3Path  # root the level arrays live under (metadata already authored there)
    store: S3Store | None  # S3 connection for a remote write, else None (local filesystem)
    channel: int  # leading-axis index this writer owns
    levels: tuple[ScaleLevel, ...]  # pyramid levels to write — one ArrayWriter each
    batch_z: int  # L0 depth per batch → maps batch_idx to its z-range
    volume_z: int  # total L0 depth → clamps the final partial batch


@dataclass(frozen=True)
class BatchResult:
    """What the worker returns for one batch: absolute UTC timestamps for its processing (downsample)
    and flushing (write) stages, plus bytes written. Absolute rather than durations, so the writer can
    place these on the same timeline as the main-process collecting/transferring spans and see overlap."""

    process_started: datetime
    process_ended: datetime
    flush_started: datetime
    flush_ended: datetime
    flushed_bytes: int


# ---------------------------------------------------------------------------
# Worker-side state (lives inside the child process). The initializer attaches to the shared-memory
# segments once; bind_output opens the per-level writers; each task reuses both.
# ---------------------------------------------------------------------------

_WORKER_SHMS: list[SharedMemory] = []
_WORKER_ARRAYS: dict[ScaleLevel, np.ndarray] = {}
_WORKER_WRITERS: dict[ScaleLevel, ArrayWriter] = {}
_WORKER_STATE: dict[str, OutputSetup] = {}  # holds the current "setup"; a dict to avoid a global rebind


def _worker_init(shm_layout: list[tuple[int, str, tuple[int, int, int]]], dtype_str: str) -> None:
    """Runs once per worker on startup: attach to the shared-memory segments (one per level)."""
    # Ignore SIGINT/Ctrl+C in workers: on Windows CTRL_C_EVENT hits the whole process group, so
    # otherwise each worker blocked in the pool's call queue dumps a KeyboardInterrupt traceback.
    # The parent handles the interrupt and tears the pool down via the normal close() path.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    # Force the single-threaded-safe numba layer in this worker (one Python thread per worker).
    os.environ["NUMBA_THREADING_LAYER"] = "workqueue"
    for level_value, shm_name, shape in shm_layout:
        shm = SharedMemory(name=shm_name, create=False, track=False)
        arr = np.ndarray(shape, dtype=dtype_str, buffer=shm.buf)
        _WORKER_SHMS.append(shm)
        _WORKER_ARRAYS[ScaleLevel(level_value)] = arr


def _worker_bind_output(setup: OutputSetup) -> None:
    """Open one ArrayWriter per level for this dataset (closing any from a previous one). The arrays'
    metadata must already exist under ``author_root`` (the main process authors it before binding)."""
    for writer in _WORKER_WRITERS.values():
        writer.close()
    _WORKER_WRITERS.clear()
    for level in setup.levels:
        writer = setup.backend()
        writer.open(setup.author_root / str(level.value), setup.store)
        _WORKER_WRITERS[level] = writer
    _WORKER_STATE["setup"] = setup


def _worker_close_output() -> None:
    """Close the per-level writers (drain pending writes, release handles)."""
    for writer in _WORKER_WRITERS.values():
        writer.close()
    _WORKER_WRITERS.clear()


def _worker_process_and_write(max_level_value: int, filled_l0: int, batch_idx: int) -> BatchResult:
    """Downsample the collected L0 block into the pyramid (in shared memory), then write every level to
    the store. Runs entirely in the worker process, so the compress+write never touches the main GIL."""
    setup = _WORKER_STATE.get("setup")
    if setup is None:
        raise RuntimeError("worker has no OutputSetup; call bind_output before flush")
    max_level = ScaleLevel(max_level_value)

    process_started = datetime.now(UTC)
    block = _WORKER_ARRAYS[ScaleLevel.L0][:filled_l0]
    pyramid = pyramids_3d_numba(block, max_level, parallel=True)
    for level, vol in pyramid.items():
        arr = _WORKER_ARRAYS[level]
        z = min(arr.shape[0], vol.shape[0])
        y = min(arr.shape[1], vol.shape[1])
        x = min(arr.shape[2], vol.shape[2])
        arr[:z, :y, :x] = vol[:z, :y, :x].astype(arr.dtype)

    process_ended = datetime.now(UTC)  # also the flush start — the write begins as soon as the pyramid is ready
    z_start = batch_idx * setup.batch_z
    z_end = min(z_start + setup.batch_z, setup.volume_z)
    flushed = 0
    for level in setup.levels:
        z0, z1 = z_start // level.factor, z_end // level.factor
        flushed += _WORKER_WRITERS[level].write_slice(setup.channel, z0, _WORKER_ARRAYS[level][: z1 - z0])

    return BatchResult(
        process_started=process_started,
        process_ended=process_ended,
        flush_started=process_ended,
        flush_ended=datetime.now(UTC),
        flushed_bytes=flushed,
    )


# ---------------------------------------------------------------------------
# Main-process slot
# ---------------------------------------------------------------------------


class BatchSlot:
    """A ring slot backed by SharedMemory whose worker downsamples and writes each batch to the store."""

    def __init__(self, name: str, shape_l0: UIVec3D, max_level: ScaleLevel, dtype: Dtype) -> None:
        self.name = name
        self.shape_l0 = shape_l0
        self.max_level = max_level
        self._dtype = dtype.dtype
        self._dtype_str = np.dtype(self._dtype).str
        self.filled_l0 = 0
        self.batch_idx: int | None = None

        self._lock = threading.Lock()
        self._stage = SlotStage.IDLE  # explicit stage while no task is in flight (IDLE / COLLECTING)
        self._future: Future[BatchResult] | None = None  # set by flush(); stage derives from it

        # Allocate one shared-memory segment per level (L0 + pyramid), prefaulted off the capture path.
        self._shms: dict[ScaleLevel, SharedMemory] = {}
        self._arrays: dict[ScaleLevel, np.ndarray] = {}
        shm_layout: list[tuple[int, str, tuple[int, int, int]]] = []
        try:
            for level in self.max_level.levels:
                shp = level.scale(self.shape_l0)
                shape = (shp.z, shp.y, shp.x)
                nbytes = int(np.prod(shape)) * self._dtype.itemsize
                shm_name = f"{self.name}_{level.value}"
                shm = SharedMemory(name=shm_name, create=True, size=nbytes, track=False)
                arr = np.ndarray(shape, dtype=self._dtype, buffer=shm.buf)
                _prefault_zero(arr)
                self._shms[level] = shm
                self._arrays[level] = arr
                shm_layout.append((level.value, shm_name, shape))
        except Exception:
            self._release_shms()
            raise

        # Force 'spawn' — the main process is multi-threaded and fork-after-thread is a deadlock hazard.
        ctx = mp.get_context("spawn")
        self._executor = ProcessPoolExecutor(
            max_workers=1,
            mp_context=ctx,
            initializer=_worker_init,
            initargs=(shm_layout, self._dtype_str),
        )

    @property
    def stage(self) -> SlotStage:
        """Current stage. While a batch task is in flight the stage derives from its future (so a
        completed batch reads IDLE without waiting on a done-callback); otherwise it's the explicit
        IDLE/COLLECTING set by assign_batch."""
        fut = self._future
        if fut is None:
            return self._stage
        if not fut.done():
            return SlotStage.PROCESSING
        return SlotStage.ERROR if fut.exception() is not None else SlotStage.IDLE

    def bind_output(self, setup: OutputSetup) -> None:
        """Open the worker's per-level writers for a dataset. Call once per dataset before the first
        batch; blocks until the writers are open."""
        self._executor.submit(_worker_bind_output, setup).result()

    def assign_batch(self, batch_idx: int) -> None:
        """Prepare an IDLE (empty) slot to collect a new batch."""
        if self.stage != SlotStage.IDLE:
            raise ValueError(f"assign_batch requires an IDLE slot, got {self.stage.name}")
        self._future = None
        self._stage = SlotStage.COLLECTING
        self.batch_idx = batch_idx
        self.filled_l0 = 0

    def add_frame(self, frame: np.ndarray, z_idx: int) -> None:
        """Write one frame into the L0 buffer at ``z_idx`` (main process)."""
        _, y0, x0 = self.shape_l0
        if frame.shape != (y0, x0):
            raise ValueError(f"Frame shape {frame.shape} does not match L0 frame {(y0, x0)}")
        if z_idx < 0 or z_idx >= self.shape_l0.z:
            raise IndexError(f"z_idx {z_idx} is outside L0 depth {self.shape_l0.z}")
        with self._lock:
            self._arrays[ScaleLevel.L0][z_idx, :y0, :x0] = frame.astype(self._dtype, copy=False)
            self.filled_l0 = max(self.filled_l0, z_idx + 1)

    def flush(self) -> Future[BatchResult]:
        """Flush the collected batch to the store: kick off the worker's downsample-and-write and return
        its future. **Asynchronous** — the work runs in the worker; the returned future resolves (to a
        `BatchResult`) when the batch is durably written. The slot is not reusable until it settles, so
        the caller waits on it before reassigning."""
        if self.batch_idx is None:
            raise RuntimeError("cannot flush a slot with no batch assigned")
        self._future = self._executor.submit(
            _worker_process_and_write, self.max_level.value, self.filled_l0, self.batch_idx
        )
        return self._future

    def close(self) -> None:
        """Close the worker's writers, shut the worker down, then unlink the shared memory."""
        try:
            self._executor.submit(_worker_close_output).result()
        except Exception:
            log.debug("Error closing output writers for %s", self.name, exc_info=True)
        finally:
            self._executor.shutdown(wait=True)
            self._release_shms()

    def _release_shms(self) -> None:
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
