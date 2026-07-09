"""Picklability of ``OutputSetup`` — it crosses the spawn boundary to the BatchSlot worker.

The scary case is `DirectS3`, whose ``target`` is a cloudpathlib ``S3Path`` bound to an ``S3Client``:
if that doesn't pickle, the worker can't receive a direct-S3 output and we'd have to pass the target
unbound (tensorstore opens from the path + store, not from the cloudpathlib client). Local and staged
outputs use a plain local ``Path``, which is trivially picklable.
"""

import os
import pickle
from pathlib import Path

import numpy as np
import pytest
from cloudpathlib import S3Path
from vxlib.vec import UIVec3D, UVec3D

from ome_zarr_writer import DirectS3, S3Store, ScaleLevel, WriterConfig
from ome_zarr_writer.array import ArrayWriter
from ome_zarr_writer.array.ts import TSArrayReader
from ome_zarr_writer.slot import BatchSlot, OutputSetup


def _roundtrip(setup: OutputSetup) -> OutputSetup:
    return pickle.loads(pickle.dumps(setup))


def test_output_setup_pickle_local() -> None:
    setup = OutputSetup(
        backend=ArrayWriter.Backend.TS,
        author_root=Path("/data/exp.ome.zarr"),  # local (Local or StagedS3 scratch)
        store=None,
        channel=0,
        levels=(ScaleLevel.L0, ScaleLevel.L1),
        batch_z=128,
        volume_z=512,
    )
    assert _roundtrip(setup) == setup


def test_output_setup_pickle_direct_s3() -> None:
    store = S3Store(endpoint="http://localhost:9000", region="us-east-1")
    storage = DirectS3(target=S3Path("s3://bucket/exp.ome.zarr"), store=store)  # binds an S3Client to target
    setup = OutputSetup(
        backend=ArrayWriter.Backend.TS,
        author_root=storage.target,  # a client-bound S3Path — the real picklability question
        store=store,
        channel=0,
        levels=(ScaleLevel.L0,),
        batch_z=128,
        volume_z=512,
    )
    r = _roundtrip(setup)
    assert str(r.author_root) == str(setup.author_root)
    assert r.store == setup.store
    assert r.backend == setup.backend and r.levels == setup.levels and r.channel == setup.channel


@pytest.mark.slow
def test_batchslot_roundtrip(tmp_path: Path) -> None:
    """End-to-end: a BatchSlot's worker downsamples and writes each batch to a local store; read L0 back
    and verify every frame's value survived. Exercises spawn + bind_output + flush + slot reuse across
    successive batches (the worker opens the writers once, the slot is reassigned after each flush)."""
    z, y, x = 6, 64, 64
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=z, y=y, x=x), voxel_size=UVec3D(z=1.0, y=0.5, x=0.5), max_level=ScaleLevel.L1
    )
    batch_z = cfg.batch_z
    assert batch_z == 2 and z % batch_z == 0  # three full batches

    root = Path(f"{tmp_path / 'ds'}.ome.zarr")
    cfg.dataset.write_metadata(root)  # arrays must exist before the worker opens them
    setup = OutputSetup(
        backend=ArrayWriter.Backend.TS,
        author_root=root,
        store=None,
        channel=0,
        levels=tuple(cfg.dataset.arrays),
        batch_z=batch_z,
        volume_z=z,
    )

    slot = BatchSlot(name=f"bstest_{os.getpid()}", shape_l0=cfg.batch_shape, max_level=cfg.max_level, dtype=cfg.dtype)
    try:
        slot.bind_output(setup)
        for b in range(z // batch_z):
            slot.assign_batch(b)
            for i in range(batch_z):
                slot.add_frame(np.full((y, x), b * batch_z + i + 1, dtype=np.uint16), i)
            result = slot.flush().result()  # waits for the worker's downsample + write
            assert result.flushed_bytes > 0
            assert result.process_started <= result.process_ended <= result.flush_ended
    finally:
        slot.close()

    arr = TSArrayReader(root / "0").read_3d(z0=0, n=z)
    assert arr.shape == (z, y, x)
    for k in range(z):
        assert int(arr[k].min()) == k + 1 and int(arr[k].max()) == k + 1, f"frame {k} corrupted"


@pytest.mark.slow
def test_batchslot_concurrent_writers(tmp_path: Path) -> None:
    """Several BatchSlot workers write disjoint, shard-aligned z-ranges of the SAME arrays concurrently
    — exactly what the ring does. This is the assumption the whole worker-flush design rests on: with
    batch_z == shard_z (L6 here), each batch owns whole shards, so concurrent writers from different
    processes never touch the same shard. Distinct per-slice values mean any cross-writer clobber shows
    up as a wrong value on read-back."""
    n_slots, batch_z = 3, 64
    z, y, x = n_slots * batch_z, 64, 64  # 192 frames = 3 shard-aligned batches
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=z, y=y, x=x), voxel_size=UVec3D(z=1.0, y=0.5, x=0.5), max_level=ScaleLevel.L6
    )
    assert cfg.batch_z == batch_z and cfg.shard_shape.z == batch_z  # shard-aligned: one batch = whole shard(s)

    root = Path(f"{tmp_path / 'ds'}.ome.zarr")
    cfg.dataset.write_metadata(root)
    setup = OutputSetup(
        backend=ArrayWriter.Backend.TS,
        author_root=root,
        store=None,
        channel=0,
        levels=tuple(cfg.dataset.arrays),
        batch_z=batch_z,
        volume_z=z,
    )

    slots = [
        BatchSlot(name=f"cw_{os.getpid()}_{s}", shape_l0=cfg.batch_shape, max_level=cfg.max_level, dtype=cfg.dtype)
        for s in range(n_slots)
    ]
    try:
        for slot in slots:
            slot.bind_output(setup)
        # Assign each slot a distinct batch and fill it, then kick off every flush so the worker
        # downsample+writes run in separate processes concurrently against the same arrays.
        for b, slot in enumerate(slots):
            slot.assign_batch(b)
            for i in range(batch_z):
                slot.add_frame(np.full((y, x), b * batch_z + i + 1, dtype=np.uint16), i)
        futures = [slot.flush() for slot in slots]
        results = [fut.result() for fut in futures]
        assert all(r.flushed_bytes > 0 for r in results)
    finally:
        for slot in slots:
            slot.close()

    arr = TSArrayReader(root / "0").read_3d(z0=0, n=z)
    assert arr.shape == (z, y, x)
    for k in range(z):
        assert int(arr[k].min()) == k + 1 and int(arr[k].max()) == k + 1, f"slice {k} corrupted"
