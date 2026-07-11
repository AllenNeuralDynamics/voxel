"""OME-Zarr writer that separates dataset lifetime from buffer-resource lifetime.

The module provides two objects:

- :class:`DatasetWriter` writes one multiscale OME-Zarr dataset (a single stack + channel) from a
  frame stream, using a ring of buffer slots supplied by the caller. It borrows the ring for its
  lifetime and never closes it; it owns and releases the remaining per-dataset resources (the
  per-level array writers, the thread pools, and the batch metrics).
- :class:`OMEZarrWriter` is a per-camera coordinator that owns a reusable :class:`Ring` and writes a
  sequence of datasets with it, one :class:`DatasetWriter` per volume. Because the ring — the only
  resource whose allocation is expensive — is retained across volumes, it is allocated once per frame
  geometry rather than once per volume.

    writer = OMEZarrWriter(slots=5)
    for config, storage in volumes:
        writer.begin_stack(config, storage)
        for frame in frames:
            writer.add_frame(frame)
        writer.end_stack()
    writer.close()
"""

import json
import logging
import math
import threading
from collections.abc import Generator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Any, Self, cast

import numpy as np
from cloudpathlib import S3Path
from pydantic import BaseModel, ConfigDict, Field
from vxlib.vec import UIVec3D, UVec3D

from ome_zarr_writer.array import ArrayWriter
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
from ome_zarr_writer.slot import BatchResult, BatchSlot, OutputSetup, SlotStage
from ome_zarr_writer.storage import Local, S3Store, StagedS3, StagingConfig, Storage
from ome_zarr_writer.transfer import TransferJob, run_s5cmd

log = logging.getLogger(__name__)

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
    downscale_type: DownscaleType = Field(
        default=DownscaleType.GAUSSIAN,
        description="Pyramid downsample method. Gaussian (anti-aliased) is the default for display-quality",
    )
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
    def batch_shape(self) -> UIVec3D:
        """L0 shape of a single batch: one batch deep (``batch_z``) and the full frame in y/x.

        Depends only on ``batch_z`` and the frame extent, not on ``volume_shape.z`` (which sets the
        number of batches, not their shape). A buffer ring sized to this shape therefore serves any
        volume with the same frame geometry, batch depth, dtype, and ``max_level``, regardless of frame
        count.
        """
        return UIVec3D(z=self.batch_z, y=self.volume_shape.y, x=self.volume_shape.x)

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


@dataclass(frozen=True)
class Ring:
    """A ring of :class:`BatchSlot`s together with the batch geometry they were allocated for.

    The owner (an :class:`OMEZarrWriter`) allocates the ring once and reuses it across datasets whenever
    the geometry matches; :meth:`close` tears every slot down (its worker + shared memory), concurrently.
    A :class:`DatasetWriter` borrows the ring and never closes it; :meth:`bind_output` points every slot's
    worker at one dataset's arrays.
    """

    slots: tuple[BatchSlot, ...]
    batch_shape: UIVec3D
    max_level: ScaleLevel
    dtype: Dtype

    @classmethod
    def allocate(cls, *, slots: int, prefix: str, batch_shape: UIVec3D, max_level: ScaleLevel, dtype: Dtype) -> "Ring":
        """Allocate `slots` BatchSlots for one batch geometry, built concurrently (each spawns a worker
        and prefaults its shared memory)."""

        def _build(i: int) -> BatchSlot:
            return BatchSlot(name=f"{prefix}_{i}", shape_l0=batch_shape, max_level=max_level, dtype=dtype)

        with ThreadPoolExecutor(max_workers=min(slots, 8)) as pool:
            built = tuple(pool.map(_build, range(slots)))
        return cls(slots=built, batch_shape=batch_shape, max_level=max_level, dtype=dtype)

    def matches(self, batch_shape: UIVec3D, max_level: ScaleLevel, dtype: Dtype) -> bool:
        """Whether this ring's slots have the given batch shape, pyramid depth, and dtype."""
        return self.batch_shape == batch_shape and self.max_level == max_level and self.dtype == dtype

    def bind_output(self, setup: OutputSetup) -> None:
        """Point every slot's worker at the dataset described by `setup` (open its per-level writers)."""
        for slot in self.slots:
            slot.bind_output(setup)

    def close(self) -> None:
        """Tear every slot down (shut its worker, unmap its shared memory), concurrently so the OS page
        reclaim of the (tens-of-GB) segments overlaps across slots."""
        if len(self.slots) <= 1:
            for slot in self.slots:
                slot.close()
            return
        with ThreadPoolExecutor(max_workers=len(self.slots)) as pool:
            list(pool.map(lambda s: s.close(), self.slots))

    def __len__(self) -> int:
        return len(self.slots)

    def __iter__(self):
        return iter(self.slots)

    def __getitem__(self, idx: int) -> BatchSlot:
        return self.slots[idx]


class DatasetWriter:
    """Writes one multiscale OME-Zarr dataset (a single stack + channel) from a frame stream, using a
    ring of :class:`BatchSlot`s supplied by the caller.

    Frames are ingested via :meth:`add_frame`; each fills the current slot until a batch is complete,
    then the slot's worker downsamples **and** writes that batch to the store — off the main process, so
    the compress+write never contends with the caller's capture loop. The main process only feeds frames
    and waits on the per-batch flush futures (for slot reuse and at close). The ring is borrowed: the
    writer drives the slots but never closes them, leaving every slot IDLE on :meth:`close` for reuse.

    Metadata is authored (main process) before binding; then each slot's worker opens the arrays. For a
    `StagedS3` storage the worker writes shards to local scratch and the main process uploads them per
    batch (s5cmd) as each flush completes; `Local`/`DirectS3` write straight to the target.
    """

    def __init__(
        self,
        config: WriterConfig,
        storage: Storage,
        ring: Ring,
        *,
        backend: ArrayWriter.Backend,
    ) -> None:
        if not ring.matches(config.batch_shape, config.max_level, config.dtype):
            raise ValueError(
                f"ring geometry {ring.batch_shape}/{ring.max_level}/{ring.dtype} does not match writer "
                f"config {config.batch_shape}/{config.max_level}/{config.dtype}"
            )
        if len(ring) < 2:
            raise ValueError(f"ring needs at least 2 slots, got {len(ring)}")

        self._config = config
        self._storage = storage
        self._ring = ring  # borrowed for this writer's lifetime; never closed here
        self._slot_count = len(ring)

        self._channel = config.channel_index
        self._volume_z = config.volume_shape.z
        self._levels = list(config.dataset.arrays)
        self._shard_z = config.dataset.shard_shape.z
        self._batch_z = config.batch_z
        self._staging = storage.tuning if isinstance(storage, StagedS3) else None  # upload tuning, iff staged
        self._store: S3Store | None = None if isinstance(storage, Local) else storage.store  # S3 connection, iff remote
        self._target = _as_ome_zarr(storage.target)  # concrete dataset location: base target + .ome.zarr

        # Author metadata (main process) before the workers open the arrays. When staging, arrays are
        # authored at scratch (mirroring the upload); else straight at the dataset target.
        scratch = storage.scratch if isinstance(storage, StagedS3) else None
        config.dataset.write_metadata(self._target)
        if scratch is not None:
            config.dataset.write_metadata(scratch)
        author_root = scratch if scratch is not None else self._target

        # Point every slot's worker at this dataset's arrays. The worker does the downsample AND the
        # write, so the main process opens no array writers of its own.
        ring.bind_output(
            OutputSetup(
                backend=backend,
                author_root=author_root,
                store=self._store,
                channel=self._channel,
                levels=tuple(self._levels),
                batch_z=self._batch_z,
                volume_z=self._volume_z,
                reduction=config.downscale_type,
            )
        )

        # Staged upload (main-side): the worker writes shards to scratch; the main process uploads them
        # per batch (s5cmd) as each flush completes. A semaphore bounds in-flight uploads so scratch
        # can't grow unbounded (backpressure onto the capture loop). Idle for Local/DirectS3.
        self._upload_pool = ThreadPoolExecutor(max_workers=1)
        self._upload_slots = threading.Semaphore(self._staging.max_pending if self._staging else 1)
        self._uploads: list[Future[None]] = []

        # In-flight batch flushes: slot index → (batch index, its BatchResult future). The worker does
        # the downsample+write; the future resolves when the batch is durable. A slot isn't reusable
        # until its flush is harvested (metrics recorded, upload queued).
        self._inflight: dict[int, tuple[int, Future[BatchResult]]] = {}

        # Pipeline cursor for this dataset. Batch assignment is lazy — the first frame of each batch
        # promotes the current slot from IDLE to COLLECTING (see add_frame).
        self._frames_added = 0
        self._next_batch_idx = 0
        self._current_slot = 0
        self._batches = BatchMetrics.create_many(self._volume_z, self._batch_z)  # one record per batch, by index

    @property
    def target(self) -> Path | S3Path:
        """The concrete dataset location this writer writes to (the storage base + ``.ome.zarr``)."""
        return self._target

    @property
    def ready_for_batch(self) -> bool:
        """Whether the next batch can be collected without blocking: at least one ring slot is IDLE."""
        return any(slot.stage == SlotStage.IDLE for slot in self._ring)

    @property
    def batches(self) -> list[BatchMetrics]:
        """The per-batch metrics records for this dataset, indexed by batch."""
        return self._batches

    def add_frame(self, frame: np.ndarray) -> None:
        """Add one frame. On a batch boundary, hand the filled batch to its slot's worker to downsample
        and write, then rotate to the next slot (waiting if that slot's flush hasn't finished)."""
        if self._frames_added >= self._volume_z:
            raise RuntimeError(f"volume complete: {self._frames_added}/{self._volume_z} frames")
        slot = self._ring[self._current_slot]
        if slot.stage == SlotStage.IDLE:  # first frame of a new batch
            slot.assign_batch(self._next_batch_idx)
            self._batches[self._next_batch_idx].collecting.begin()
            self._next_batch_idx += 1
        if slot.batch_idx is None:  # narrowing: assigned above, or on a prior frame of this batch
            raise RuntimeError("slot has no batch assigned")
        slot.add_frame(frame, self._frames_added % self._batch_z)
        self._batches[slot.batch_idx].collected_frames += 1
        self._frames_added += 1
        if self._frames_added % self._batch_z == 0 and self._frames_added < self._volume_z:
            self._flush_current()  # hand the filled batch to its worker (downsample + write)
            # Rotate to the next slot. If its flush hasn't finished, wait — the backpressure that blocks
            # the caller once every slot is occupied; a no-op while the ring has spare slots.
            nxt = (self._current_slot + 1) % self._slot_count
            if nxt in self._inflight:
                self._harvest(nxt)  # wait for the slot's flush → record metrics, queue upload, slot IDLE
            self._current_slot = nxt
            self._reap()  # harvest any completed flushes (metrics + uploads), surfacing failures
            if self._staging is not None:
                self._reap_uploads()  # surface a failed upload promptly rather than acquiring into a doomed run

    def close(self) -> None:
        """Flush the final (often partial) batch, harvest every in-flight flush, finish uploads, then
        release this writer's own resources (the upload pool). The ring is left untouched — every slot
        IDLE — for reuse by its owner. Raises if a flush or upload failed."""
        slot = self._ring[self._current_slot]
        if slot.filled_l0 > 0 and slot.stage == SlotStage.COLLECTING:  # the final partial batch
            self._flush_current()

        # Harvest every outstanding flush (records metrics, queues its upload); collect the first failure
        # but always finish teardown. Uploads are all queued once the flushes settle, so drain them next.
        flush_error: BaseException | None = None
        for slot_idx in list(self._inflight):
            try:
                self._harvest(slot_idx)
            except Exception as exc:
                flush_error = flush_error or exc
        upload_error = self._drain_uploads()
        self._upload_pool.shutdown(wait=True)
        self._log_timing_summary()
        self._write_batch_metrics()
        error = flush_error or upload_error
        if error is not None:
            raise error

    def _write_batch_metrics(self) -> None:
        """Persist per-batch metrics as ``metrics.json`` inside the dataset for later analysis: each
        batch's per-stage timing (absolute start/end, so overlap and gaps are recoverable) and byte
        counts, plus enough run context to be self-describing. Best-effort — a metrics-write failure
        must never fail the run."""
        payload = {
            "schema_version": 1,
            "target": str(self._target),
            "batch_z": self._batch_z,
            "slots": self._slot_count,
            "config": self._config.model_dump(mode="json"),
            "batches": [b.model_dump(mode="json") for b in self._batches],
        }
        try:
            (self._target / "metrics.json").write_text(json.dumps(payload, indent=2))
        except Exception:
            log.warning("Failed to write batch metrics for %s", self._target, exc_info=True)

    def _flush_current(self) -> None:
        """Close the current batch's `collecting` span and hand it to its slot's worker to downsample and
        write; track the flush future (by slot) for reuse/harvest."""
        slot = self._ring[self._current_slot]
        if slot.batch_idx is None:  # narrowing: the slot has been collecting a batch
            raise RuntimeError("cannot flush a slot with no batch assigned")
        self._batches[slot.batch_idx].collecting.complete()
        self._inflight[self._current_slot] = (slot.batch_idx, slot.flush())

    def _harvest(self, slot_idx: int) -> None:
        """Wait for a slot's flush, record its metrics, and (when staging) queue its upload. Blocks until
        the worker's downsample+write is durable, after which the slot is IDLE (reusable)."""
        batch_idx, future = self._inflight.pop(slot_idx)
        self._record(batch_idx, future.result())  # raises if the worker's downsample/write failed
        if self._staging is not None:
            self._queue_upload(batch_idx)

    def _reap(self) -> None:
        """Harvest every already-completed flush without blocking (metrics + uploads), surfacing failures.
        Runs on the capture thread — the only thread that mutates ``_inflight``."""
        for slot_idx in [i for i, (_, fut) in self._inflight.items() if fut.done()]:
            self._harvest(slot_idx)

    def _record(self, batch_idx: int, result: BatchResult) -> None:
        """Fold a worker's `BatchResult` (absolute timestamps + bytes) into the batch's metrics — the
        worker's spans land on the same timeline as the main-timed collecting/transferring spans."""
        batch = self._batches[batch_idx]
        batch.processing.started, batch.processing.ended = result.process_started, result.process_ended
        batch.flushing.started, batch.flushing.ended = result.flush_started, result.flush_ended
        batch.flushed_bytes = result.flushed_bytes

    def _queue_upload(self, batch_idx: int) -> None:
        """Queue the s5cmd upload of a written batch's shards (staged only). Blocks if max_pending uploads
        are already in flight — the backpressure that bounds scratch growth."""
        tuning = self._staging
        if tuning is None:
            return
        z_start = batch_idx * self._batch_z
        z_end = min(z_start + self._batch_z, self._volume_z)
        jobs = self._transfer_jobs(z_start, z_end)
        self._upload_slots.acquire()
        batch = self._batches[batch_idx]
        self._uploads.append(self._upload_pool.submit(self._upload_and_evict, jobs, batch, tuning))

    def _transfer_jobs(self, z_start: int, z_end: int) -> list[TransferJob]:
        """The batch's shards as upload jobs: scratch source → S3 target, across every pyramid level
        (`dataset.shards` enumerates them; z is in L0 shard indices). Empty for a non-staged storage."""
        if not isinstance(self._storage, StagedS3):  # nothing to upload
            return []
        z_shards = range(z_start // self._shard_z, math.ceil(z_end / self._shard_z))
        dest_root = cast("S3Path", self._target)  # staged ⇒ target is an S3Path (see StagedS3)
        return [
            TransferJob(src=shard.at(self._storage.scratch), dest=shard.at(dest_root))
            for shard in self._config.dataset.shards(channels=[self._channel], z_range=z_shards)
        ]

    def _upload_and_evict(self, jobs: list[TransferJob], batch: BatchMetrics, tuning: StagingConfig) -> None:
        """Upload one batch's shards (s5cmd), then delete the local copies — each step measured into
        `batch`. Runs on the upload pool. A failed upload skips eviction (sources are kept) and surfaces
        via the future."""
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
        """Re-raise the first settled-and-failed upload; keep the unsettled ones. ``_uploads`` is
        touched only on the capture thread (queued in _harvest, reaped here)."""
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

    def _log_timing_summary(self) -> None:
        """Log per-stack totals for each pipeline stage (downsample vs flush-to-store vs upload). Spans
        overlap under concurrency, so the totals indicate relative magnitude per stage, not wall-clock."""

        def _secs(t: "Timing") -> float:
            return (t.ended - t.started).total_seconds() if t.started and t.ended else 0.0

        batches = self._batches
        if not batches:
            return
        stages = ("collecting", "processing", "flushing", "transferring", "evicting")
        totals = {name: sum(_secs(getattr(b, name)) for b in batches) for name in stages}
        log.info(
            "Writer timing for %s (%d batches): collect=%.1fs process=%.1fs flush=%.1fs "
            "transfer=%.1fs evict=%.1fs | flushed=%.2f GB transferred=%.2f GB",
            self._target,
            len(batches),
            totals["collecting"],
            totals["processing"],
            totals["flushing"],
            totals["transferring"],
            totals["evicting"],
            sum(b.flushed_bytes for b in batches) / 1e9,
            sum(b.transfered_bytes for b in batches) / 1e9,
        )


class OMEZarrWriter:
    """Per-camera coordinator that owns a reusable :class:`Ring` and writes a sequence of datasets.

    Each volume is written by a fresh :class:`DatasetWriter` created in :meth:`begin_stack` and closed in
    :meth:`end_stack`. The ring is retained between volumes and reused whenever the frame geometry is
    unchanged; a change in batch shape, pyramid depth, or dtype triggers a single reallocation for the
    new geometry. :meth:`close` releases the ring at the end of the acquisition.

        writer = OMEZarrWriter(slots=5)
        writer.begin_stack(config, storage)
        writer.add_frame(frame)
        ...
        writer.end_stack()
        ...
        writer.close()
    """

    def __init__(
        self,
        *,
        backend: ArrayWriter.Backend = ArrayWriter.Backend.TS,
        slots: int = 4,  # ring depth = max batches in flight (caller sizes from its RAM share)
    ) -> None:
        self._backend = backend
        self._slots = slots
        self._ring: Ring | None = None
        self._active: DatasetWriter | None = None

    @property
    def ready_for_batch(self) -> bool:
        """Whether the next batch can be collected without blocking: True when no dataset is open, or the
        open dataset has at least one IDLE slot."""
        return self._active is None or self._active.ready_for_batch

    @property
    def batches(self) -> list[BatchMetrics]:
        """The per-batch metrics of the open dataset, or an empty list when none is open."""
        return self._active.batches if self._active is not None else []

    @property
    def target(self) -> Path | S3Path | None:
        """The location of the open dataset, or None when none is open."""
        return self._active.target if self._active is not None else None

    def begin_stack(self, config: WriterConfig, storage: Storage) -> DatasetWriter:
        """Open a dataset for one volume and return its writer. Reuses the retained ring when its
        geometry matches `config`; otherwise releases it and allocates a ring for the new geometry."""
        if self._active is not None:
            raise RuntimeError("stack already open; call end_stack() first")
        if (
            self._ring is None
            or len(self._ring) != self._slots
            or not self._ring.matches(config.batch_shape, config.max_level, config.dtype)
        ):
            self._drop_ring()
            self._ring = Ring.allocate(
                slots=self._slots,
                prefix=f"ozw_{id(self):x}",  # stable across reuses so retained segments keep their names
                batch_shape=config.batch_shape,
                max_level=config.max_level,
                dtype=config.dtype,
            )
        self._active = DatasetWriter(config, storage, self._ring, backend=self._backend)
        return self._active

    def add_frame(self, frame: np.ndarray) -> None:
        """Add one frame to the open dataset."""
        if self._active is None:
            raise RuntimeError("no stack open; call begin_stack() first")
        self._active.add_frame(frame)

    def end_stack(self) -> None:
        """Drain and close the open dataset, retaining the ring for the next volume. If the dataset's
        close fails, the ring is released so that a slot left mid-processing is not reused."""
        if self._active is None:
            raise RuntimeError("no stack open")
        try:
            self._active.close()
        except Exception:
            self._drop_ring()
            raise
        finally:
            self._active = None

    def close(self) -> None:
        """Close any open dataset and release the ring."""
        try:
            if self._active is not None:
                self._active.close()
        finally:
            self._active = None
            self._drop_ring()

    def _drop_ring(self) -> None:
        """Release the retained ring, if any."""
        if self._ring is not None:
            self._ring.close()
            self._ring = None
