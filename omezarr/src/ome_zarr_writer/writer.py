"""`OMEZarrWriter`: a self-contained writer for one OME-Zarr dataset (a single stack + channel).

Frames are ingested one at a time, batched into a ring, downsampled asynchronously, and flushed
to per-level array writers. The `Storage` passed to the writer selects where shards land: a
`StagedS3` writes each batch to local scratch and uploads it to S3 (then evicts), while
`Local`/`DirectS3` write straight to the target.

Self-contained — the writer never reads system state. Batch depth (`batch_z`) comes from the
config's policy knobs; the caller sizes the ring `slots` from its own RAM share.
"""

import math
import threading
from collections.abc import Generator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Any, Self, cast

import numpy as np
from cloudpathlib import S3Path
from pydantic import BaseModel, ConfigDict, Field
from vxlib.vec import UIVec3D, UVec3D

from ome_zarr_writer.array import ArrayWriter
from ome_zarr_writer.buffer import BufferSlot, BufferStage, PyramidRingBuffer
from ome_zarr_writer.dataset import (
    Compression,
    DownscaleType,
    Dtype,
    OmeZarrDataset,
    ScaleLevel,
    SpaceUnit,
    Zarr3ArrayMeta,
    Zarr3GroupMeta,
)
from ome_zarr_writer.storage import Local, S3Store, StagedS3, StagingConfig, Storage
from ome_zarr_writer.transfer import TransferJob, run_s5cmd

# Floor for the base (L0) chunk edge: chunks never fall below 64 voxels per axis, regardless of level.
MIN_CHUNK_EDGE = 64

OME_ZARR_SUFFIX = ".ome.zarr"


def _as_ome_zarr(path: Path | S3Path) -> Path | S3Path:
    """`path` named as an OME-Zarr dataset (a trailing ``.ome.zarr``); idempotent. The writer owns
    this naming convention — a `Storage` carries only the base location."""
    return path if path.name.endswith(OME_ZARR_SUFFIX) else path.parent / f"{path.name}{OME_ZARR_SUFFIX}"


class WriterSettings(BaseModel):
    """Output-format settings applied during acquisition. Broadcast uniformly to every camera so all
    channels produce a coherent dataset; the camera conforms or raises. Mutable — it's an editable
    fragment of the controller's bench state."""

    model_config = ConfigDict(extra="forbid")

    # sync-critical (determine batch_z)
    max_level: ScaleLevel = Field(default=ScaleLevel.L7, description="Maximum pyramid downscale level")
    shard_z_chunks: int = 1
    batch_z_shards: int = 1
    # coherence (uniform for a consistent dataset; camera conforms)
    compression: Compression = Field(default=Compression.BLOSC_LZ4, description="Compression codec for zarr chunks")
    downscale_type: DownscaleType = DownscaleType.MEAN
    target_shard_gb: float = 1.0

    @property
    def chunk_shape(self) -> UIVec3D:
        # Base (L0) chunk is a cube of edge 2^max_level, floored at MIN_CHUNK_EDGE.
        edge = max(MIN_CHUNK_EDGE, self.max_level.factor)
        return UIVec3D(z=edge, y=edge, x=edge)

    @property
    def batch_z(self) -> int:
        return self.batch_z_shards * self.shard_z_chunks * self.max_level.factor


class WriterConfig(WriterSettings):
    """The dataset spec for a writer run — acquisition geometry plus the output-format knobs
    inherited from :class:`WriterSettings`. Frozen; its ``dataset`` is cached, which immutability
    keeps sound. *Where* the run is written is a separate :class:`Storage` passed to the writer."""

    model_config = ConfigDict(frozen=True)

    # acquisition geometry
    volume_shape: UIVec3D
    voxel_size: UVec3D
    voxel_unit: SpaceUnit = SpaceUnit.MICROMETER
    dtype: Dtype = Dtype.UINT16
    channel_index: int = 0

    @cached_property
    def shard_shape(self) -> UIVec3D:
        c_bytes = self.dtype.calc_nbytes(self.chunk_shape)
        c_size_z, c_size_y, c_size_x = self.chunk_shape
        target_bytes = int(self.target_shard_gb * (1024**3))
        target_chunks = max(1, round(target_bytes / c_bytes))

        zc = self.shard_z_chunks
        per_layer = max(1, target_chunks // zc)
        yc = max(1, round(math.sqrt(per_layer)))
        xc = max(1, per_layer // yc)

        v_shape = self.volume_shape
        return UIVec3D(
            z=min(zc, max(1, v_shape.z // c_size_z)) * c_size_z,
            y=min(yc, max(1, v_shape.y // c_size_y)) * c_size_y,
            x=min(xc, max(1, v_shape.x // c_size_x)) * c_size_x,
        )

    @cached_property
    def dataset(self) -> OmeZarrDataset:
        """Resolve into the OME-Zarr v3 on-disk dataset description."""
        arrays: dict[ScaleLevel, Zarr3ArrayMeta] = {}
        for level in self.max_level.levels:
            sv = level.scale(self.volume_shape)
            ss = level.scale(self.shard_shape)
            sc = level.scale(self.chunk_shape)
            arrays[level] = Zarr3ArrayMeta.sharded(
                shape=[1, sv.z, sv.y, sv.x],
                shard_shape=[1, ss.z, ss.y, ss.x],
                chunk_shape=[1, sc.z, sc.y, sc.x],
                dtype=self.dtype,
                compression=self.compression,
                dimension_names=["c", "z", "y", "x"],
            )

        group = Zarr3GroupMeta.multiscale(
            voxel_size=self.voxel_size,
            voxel_unit=self.voxel_unit,
            max_level=self.max_level,
            downscale_type=self.downscale_type,
        )

        return OmeZarrDataset(group=group, arrays=arrays)


class Timing(BaseModel):
    started: datetime | None = None
    ended: datetime | None = None
    error: str | None = None

    def begin(self) -> None:
        """Mark the step's start. Pair with `complete()` for steps that span scopes
        (where `measure()` can't wrap a single block)."""
        self.started = datetime.now(UTC)

    def complete(self) -> None:
        """Mark the step's end."""
        self.ended = datetime.now(UTC)

    def fail(self, error: str) -> None:
        """Mark the step as failed with the given error message."""
        self.error = error
        self.ended = datetime.now(UTC)

    @contextmanager
    def measure(self) -> Generator[Self]:
        """Time a synchronous block: marks start, then ends via `complete()` on success or
        `fail()` on error. The two terminal states are mutually exclusive."""
        self.begin()
        try:
            yield self
        except Exception as e:
            self.fail(f"{type(e).__name__}: {e}")
            raise
        else:
            self.complete()

    def track(self, future: Future[Any]) -> None:
        """Time async work: mark started now, then end it — via `complete()` or `fail()` —
        when `future` resolves. The async analog of `measure()`, so the end is marked at the
        work's actual finish rather than whenever the caller later harvests it."""
        self.begin()

        def _on_done(done: Future[Any]) -> None:
            if (exc := done.exception()) is not None:
                self.fail(f"{type(exc).__name__}: {exc}")
            else:
                self.complete()

        future.add_done_callback(_on_done)


class BatchMetrics(BaseModel):
    batch_idx: int
    expected_frames: int
    collected_frames: int = 0
    flushed_bytes: int = 0
    transfered_bytes: int = 0
    collecting: Timing = Field(default_factory=Timing)
    processing: Timing = Field(default_factory=Timing)
    flushing: Timing = Field(default_factory=Timing)
    transferring: Timing = Field(default_factory=Timing)
    evicting: Timing = Field(default_factory=Timing)

    @classmethod
    def create_many(cls, total_frames: int, batch_z: int) -> list[Self]:
        n_batches = total_frames // batch_z + 1
        return [cls(batch_idx=i, expected_frames=min(batch_z, total_frames - i * batch_z)) for i in range(n_batches)]


class OMEZarrWriter:
    """Writes one multiscale OME-Zarr dataset (a single stack + channel) from a
    frame stream. Self-contained: owns its ring of buffer slots, a write pool, and
    one array writer per pyramid level for the dataset's lifetime.

    Frames are ingested one at a time via `add_frame`; each fills the current ring
    slot until a batch is complete, the slot downsamples asynchronously, and the
    result is flushed to every pyramid level. `close` drains the final (partial)
    batch and releases all resources.

        writer = OMEZarrWriter(config, storage, slots=6)
        for frame in frames:
            writer.add_frame(frame)
        writer.close()

    For a `StagedS3` storage, shards are written to local scratch and uploaded to the S3
    target per batch on a background upload pool (s5cmd), then the local copies are evicted;
    `Local`/`DirectS3` write straight to the target.
    """

    def __init__(
        self,
        config: WriterConfig,
        storage: Storage,
        *,
        backend: ArrayWriter.Backend = ArrayWriter.Backend.TS,
        ring_buffer: PyramidRingBuffer = PyramidRingBuffer.PROCESS,
        slots: int = 4,  # ring depth = max batches in flight (caller sizes from its RAM share)
    ) -> None:
        self._config = config
        self._storage = storage
        self._channel = config.channel_index
        self._volume_z = config.volume_shape.z
        self._levels = list(config.dataset.arrays)
        self._slot_count = slots
        self._shard_z = config.dataset.shard_shape.z
        self._batch_z = config.batch_z
        self._staging = storage.tuning if isinstance(storage, StagedS3) else None  # upload tuning, iff staged
        self._store: S3Store | None = None if isinstance(storage, Local) else storage.store  # S3 connection, iff remote
        self._target = _as_ome_zarr(storage.target)  # concrete dataset location: the base target + .ome.zarr

        # The ring of RAM slots (each collects one batch, then downsamples it) and a
        # pool that fans this dataset's per-level writes. Slots are sized to the batch's
        # frame geometry (batch_z, y, x).
        self._slots = ring_buffer(
            slots=slots,
            prefix=f"ozw_{id(self):x}",  # SharedMemory names must be process-unique
            shape_l0=UIVec3D(z=self._batch_z, y=config.volume_shape.y, x=config.volume_shape.x),
            max_level=config.max_level,
            dtype=config.dtype,
        )
        self._write_pool = ThreadPoolExecutor(max_workers=max(len(self._levels), 1))

        # Author metadata at the dataset target, and — when staging — at the local scratch tree too
        # (so the uploaded shards land in a valid dataset). Arrays are authored at scratch when
        # staging, else straight at the dataset target.
        scratch = storage.scratch if isinstance(storage, StagedS3) else None
        config.dataset.write_metadata(_as_ome_zarr(storage.target))  # client-bound dataset root
        if scratch is not None:
            config.dataset.write_metadata(scratch)  # local author tree (no suffix; mirrors the upload)

        author_root = scratch if scratch is not None else self._target
        self._level_writers: dict[ScaleLevel, ArrayWriter] = {}
        for level in self._levels:
            writer = backend()
            writer.open(author_root / str(level.value), self._store)
            self._level_writers[level] = writer

        # Staged upload: one background thread (max_workers=1 → groups upload serially; s5cmd
        # parallelizes within a group). The pool spawns its worker lazily, so it costs nothing
        # when not staging. A semaphore bounds the batches in flight so the flush (and thus the
        # camera) blocks before scratch grows unbounded.
        self._upload_pool = ThreadPoolExecutor(max_workers=1)
        self._upload_slots = threading.Semaphore(self._staging.max_pending if self._staging else 1)
        self._uploads: list[Future[None]] = []

        # Pipeline state. Batch assignment is lazy — the first frame of each batch
        # promotes the current slot from IDLE to COLLECTING (see `add_frame`).
        self._frames_added = 0
        self._next_batch_idx = 0
        self._current_slot = 0
        self._inflight: dict[int, Future] = {}  # slot index → its downsampling future, until flushed
        self._batches = BatchMetrics.create_many(self._volume_z, self._batch_z)  # one record per batch, by index

    @property
    def target(self) -> Path | S3Path:
        """The concrete dataset location this writer writes to (the storage base + ``.ome.zarr``)."""
        return self._target

    @property
    def ready_for_batch(self) -> bool:
        """Whether the next batch can be collected without blocking: at least one ring slot is IDLE."""
        return any(slot.stage == BufferStage.IDLE for slot in self._slots)

    @property
    def batches(self) -> list[BatchMetrics]:
        return self._batches

    def add_frame(self, frame: np.ndarray) -> None:
        """Add one frame to the pipeline. On a batch boundary, kicks off async
        downsampling for the filled slot and rotates to the next one."""
        if self._frames_added >= self._volume_z:
            raise RuntimeError(f"volume complete: {self._frames_added}/{self._volume_z} frames")
        slot = self._slots[self._current_slot]
        if slot.stage == BufferStage.IDLE:  # first frame of a new batch
            slot.assign_batch(self._next_batch_idx)
            self._batches[self._next_batch_idx].collecting.begin()
            self._next_batch_idx += 1
        assert slot.batch_idx is not None  # assigned above (or on a prior frame of this batch)
        slot.add_frame(frame, self._frames_added % self._batch_z)
        self._batches[slot.batch_idx].collected_frames += 1
        self._frames_added += 1
        if self._frames_added % self._batch_z == 0 and self._frames_added < self._volume_z:
            self._start_processing(slot)
            # Rotate to the next slot, flushing it first if it's still in flight — the
            # natural backpressure once all `slots` are occupied (the camera blocks here).
            nxt = (self._current_slot + 1) % self._slot_count
            if nxt in self._inflight:
                self._flush_slot(nxt)
            self._current_slot = nxt
            if self._staging is not None:
                self._reap_uploads()  # surface a failed upload promptly rather than acquiring into a doomed run

    def close(self) -> None:
        """Drain the final (often partial) batch, finish any uploads, then release the
        array writers, upload pool, ring slots, and write pool. Raises if an upload failed."""
        slot = self._slots[self._current_slot]
        if slot.filled_l0 > 0 and slot.stage == BufferStage.COLLECTING:  # the final partial batch
            self._start_processing(slot)
        for slot_idx in list(self._inflight):
            self._flush_slot(slot_idx)
        for writer in self._level_writers.values():
            writer.close()
        self._level_writers.clear()

        # Finish uploads before tearing down. Collect the first failure but always complete
        # teardown, then raise — so a failed upload never leaks the upload pool or slots.
        upload_error = self._drain_uploads()
        self._upload_pool.shutdown(wait=True)
        for slot in self._slots:
            slot.close()
        self._write_pool.shutdown(wait=True)
        if upload_error is not None:
            raise upload_error

    def _start_processing(self, slot: BufferSlot) -> None:
        """Close a filled slot's `collecting` span and kick off its async downsample.
        `track` opens the `processing` span and completes it when the downsample future
        resolves — so its timing reflects the actual compute, not the later harvest."""
        assert slot.batch_idx is not None  # the slot has been collecting a batch
        batch = self._batches[slot.batch_idx]
        batch.collecting.complete()
        future = slot.start_processing()
        self._inflight[self._current_slot] = future
        batch.processing.track(future)

    def _flush_slot(self, slot_idx: int) -> None:
        """Wait for a slot's downsampling to finish, write every pyramid level, and — when
        staging — queue the batch's freshly-written shards for upload."""
        self._inflight.pop(slot_idx).result()  # wait for downsampling (processing span closed by its track callback)
        slot = self._slots[slot_idx]
        assert slot.batch_idx is not None  # assign_batch runs before any frame is added
        batch = self._batches[slot.batch_idx]
        z_start = slot.batch_idx * self._batch_z
        z_end = min(z_start + self._batch_z, self._volume_z)
        with batch.flushing.measure():
            writes = [self._write_pool.submit(self._write_level, level, slot, z_start, z_end) for level in self._levels]
            batch.flushed_bytes = sum(write.result() for write in writes)
        if self._staging is not None:
            jobs = self._transfer_jobs(z_start, z_end)
            self._upload_slots.acquire()  # blocks the flush (→ camera) once max_pending are in flight
            self._uploads.append(self._upload_pool.submit(self._upload_and_evict, jobs, batch, self._staging))

    def _write_level(self, level: ScaleLevel, slot: BufferSlot, z_start: int, z_end: int) -> int:
        """Write one pyramid level's rows for a batch. The `[: z1 - z0]` slice keeps
        a partial tail batch honest — only its real rows are written, at every level."""
        z0, z1 = z_start // level.factor, z_end // level.factor
        return self._level_writers[level].write_slice(self._channel, z0, slot.get_volume(level)[: z1 - z0])

    def _transfer_jobs(self, z_start: int, z_end: int) -> list[TransferJob]:
        """The batch's shards as upload jobs: scratch source -> S3 target, across every pyramid
        level (`dataset.shards` enumerates them; z is in L0 shard indices). Empty for a
        non-staged storage (nothing to upload)."""
        if not isinstance(self._storage, StagedS3):  # nothing to upload
            return []
        z_shards = range(z_start // self._shard_z, math.ceil(z_end / self._shard_z))
        dest_root = cast("S3Path", self._target)  # staged ⇒ target is an S3Path (see StagedS3)
        return [
            TransferJob(src=shard.at(self._storage.scratch), dest=shard.at(dest_root))
            for shard in self._config.dataset.shards(channels=[self._channel], z_range=z_shards)
        ]

    def _upload_and_evict(self, jobs: list[TransferJob], batch: BatchMetrics, tuning: StagingConfig) -> None:
        """Upload one batch's shards (s5cmd), then delete the local copies — each step
        measured into `batch`. Runs on the upload pool. A failed upload skips eviction
        (sources are kept) and surfaces via the future."""
        try:
            with batch.transferring.measure():
                bytes_up = run_s5cmd(jobs, self._store, numworkers=tuning.numworkers, retry_count=tuning.retry_count)
                batch.transfered_bytes = bytes_up
            with batch.evicting.measure():
                for job in jobs:
                    if job.src.exists():
                        job.src.unlink()
        finally:
            self._upload_slots.release()

    def _reap_uploads(self) -> None:
        """Re-raise the first settled-and-failed upload; keep the unsettled ones."""
        pending: list[Future[None]] = []
        for upload in self._uploads:
            if upload.done():
                upload.result()  # re-raises a failed upload → aborts the acquisition
            else:
                pending.append(upload)
        self._uploads = pending

    def _drain_uploads(self) -> BaseException | None:
        """Block on every outstanding upload; return the first failure seen (or None)."""
        error: BaseException | None = None
        for upload in self._uploads:
            exc = upload.exception()  # blocks until the upload settles
            if error is None and exc is not None:
                error = exc
        self._uploads.clear()
        return error
