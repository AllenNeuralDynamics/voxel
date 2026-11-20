"""Async-flush correctness for both writers.

Each flushes a batch to storage on a background pool as its downsample completes, and a slot may be
reassigned only after its flush has finished reading it (the FLUSHING → IDLE ``release()``). Driving a
ring with fewer slots than batches forces the ring to *wrap*, exercising that reuse path; distinct
per-frame values mean any reuse-before-flush would corrupt the read-back, so a green round-trip proves
the invariant holds while flush overlaps capture.
"""

import time
from concurrent.futures import Future
from pathlib import Path

import numpy as np
import pytest
from ome_zarr_writer import Local, OMEZarrWriter, ScaleLevel, WriterConfig, WriterSettings
from ome_zarr_writer.array.ts import TSArrayReader
from vxlib.imaging.writer import FrameRange
from vxlib.vector import IVec2D, Transform, Vec3D


def _read_l0(base: Path, z: int) -> np.ndarray:
    return TSArrayReader(Path(f"{base}.ome.zarr") / "0").read_3d(z0=0, n=z)


@pytest.mark.slow
def test_OMEZarrWriter_async_flush_wrapping_ring_roundtrip(tmp_path: Path) -> None:  # noqa: N802
    """OMEZarrWriter DatasetWriter (via the coordinator): same wrapping-ring invariant."""
    z, y, x = 256, 64, 64
    cfg = WriterConfig(transform=Transform.grid((z, y, x), Vec3D(z=1.0, y=0.5, x=0.5)), max_level=ScaleLevel.L6)
    assert cfg.batch_frames == 64
    assert z // cfg.batch_frames == 4
    writer = OMEZarrWriter(slots=2)  # BatchSlot (process) — worker does downsample + write off the main GIL
    writer.open_dataset(cfg, Local(target=tmp_path / "v2"))
    for i in range(z):
        with writer.new_frame() as frame:
            frame.fill(i + 1)
    writer.close_image()
    writer.release()

    arr = _read_l0(tmp_path / "v2", z)
    assert arr.shape == (z, y, x)
    for i in range(z):
        assert int(arr[i].min()) == i + 1, f"frame {i} corrupted"
        assert int(arr[i].max()) == i + 1, f"frame {i} corrupted"


@pytest.mark.slow
def test_OMEZarrWriter_reuses_ring_across_stacks(tmp_path: Path) -> None:  # noqa: N802
    """A second stack on the same OMEZarrWriter reuses the resident ring; its slots must start IDLE (flushed)
    from the first stack, and each stack's data must round-trip independently."""
    z, y, x = 128, 64, 64
    cfg = WriterConfig(transform=Transform.grid((z, y, x), Vec3D(z=1.0, y=0.5, x=0.5)), max_level=ScaleLevel.L6)
    writer = OMEZarrWriter(slots=2)  # BatchSlot (process) — worker does downsample + write off the main GIL
    for stack, base in (("a", 1), ("b", 1000)):
        writer.open_dataset(cfg, Local(target=tmp_path / stack))
        for i in range(z):
            with writer.new_frame() as frame:
                frame.fill(base + i)
        writer.close_image()
    writer.release()

    for stack, base in (("a", 1), ("b", 1000)):
        arr = _read_l0(tmp_path / stack, z)
        assert int(arr[0].max()) == base, stack
        assert int(arr[z - 1].max()) == base + z - 1, stack


@pytest.mark.slow
def test_frame_abort_does_not_advance(tmp_path: Path) -> None:
    cfg = WriterConfig(
        transform=Transform.grid((1, 64, 64), Vec3D(z=1.0, y=0.5, x=0.5)),
        max_level=ScaleLevel.L0,
    )
    writer = OMEZarrWriter(slots=2)
    writer.open_dataset(cfg, Local(target=tmp_path / "abort"))
    with pytest.raises(ValueError, match="could not broadcast"), writer.new_frame() as abandoned:
        np.copyto(abandoned, np.empty(0, dtype=np.uint16))
    assert writer._ring is not None
    assert all(slot.reusable for slot in writer._ring)
    with writer.new_frame() as frame:
        frame.fill(7)
    writer.close_image()
    writer.release()

    assert int(_read_l0(tmp_path / "abort", 1)[0].max()) == 7


@pytest.mark.slow
def test_retained_frame_prevents_slot_reuse_after_processing(tmp_path: Path) -> None:
    cfg = WriterConfig(
        transform=Transform.grid((1, 64, 64), Vec3D(z=1.0, y=0.5, x=0.5)),
        max_level=ScaleLevel.L0,
    )
    writer = OMEZarrWriter(slots=2)
    writer.open_dataset(cfg, Local(target=tmp_path / "retained"))
    with writer.new_frame() as frame:
        frame.fill(11)
    lease = writer.latest_frame()
    assert lease is not None
    writer.close_image()

    assert writer._ring is not None
    retained_slot = next(slot for slot in writer._ring if slot.active_readers)
    assert retained_slot.stage.name == "IDLE"
    assert not retained_slot.reusable
    assert not lease.array.flags.writeable
    lease.close()
    assert retained_slot.reusable
    writer.release()


@pytest.mark.slow
def test_flush_failure_poisoning_is_sticky(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = WriterConfig(
        transform=Transform.grid((1, 64, 64), Vec3D(z=1.0, y=0.5, x=0.5)),
        max_level=ScaleLevel.L0,
    )
    writer = OMEZarrWriter(slots=2)
    dataset = writer.open_dataset(cfg, Local(target=tmp_path / "failed"))
    failed: Future[None] = Future()
    failed.set_exception(RuntimeError("flush failed"))
    monkeypatch.setattr(dataset._ring[0], "flush", lambda: failed)

    with writer.new_frame() as frame:
        frame.fill(1)
    lease = writer.latest_frame()
    assert lease is not None
    with pytest.raises(RuntimeError, match="flush failed"):
        dataset.close()

    assert not dataset.ready_for_batch
    with pytest.raises(RuntimeError, match="cannot continue"), dataset.new_frame():
        pass
    with pytest.raises(RuntimeError, match="flush failed"):
        writer.close_image()
    assert writer._ring is not None
    assert writer._ring_failed

    lease.close()
    writer.release()


@pytest.mark.slow
def test_a_batch_that_finds_every_slot_busy_is_dropped_whole_and_the_next_one_is_written(tmp_path: Path) -> None:
    cfg = WriterConfig(transform=Transform.grid((4 * 64, 64, 64), Vec3D(z=1.0, y=0.5, x=0.5)), max_level=ScaleLevel.L6)
    batch = cfg.batch_frames
    writer = OMEZarrWriter(slots=2)
    writer.open_image(
        Local(target=tmp_path / "drop"),
        IVec2D(x=64, y=64),
        cfg.dtype,
        cfg.transform,
        WriterSettings(max_level=ScaleLevel.L6),
        ram_bytes=0,
        when_full="drop",
    )
    leases = []
    for i in range(4 * batch):
        with writer.new_frame() as frame:
            frame.fill(i + 1)
        if i in (batch - 1, 2 * batch - 1):  # a reader holds the last frame of batches 0 and 1: both slots stay busy
            lease = writer.latest_frame()
            assert lease is not None
            leases.append(lease)
        if i == 3 * batch - 1:
            assert writer.latest_frame() is None  # the last frame of the dropped batch
            for lease in leases:
                lease.close()
            deadline = time.monotonic() + 30
            while not writer.ready_for_batch:  # the slots finish writing to disk
                assert time.monotonic() < deadline
                time.sleep(0.01)

    assert writer.dropped == [FrameRange(first=2 * batch, last=3 * batch - 1)]
    assert writer.progress.dropped == batch
    writer.close_image()
    writer.release()

    arr = _read_l0(tmp_path / "drop", 4 * batch)
    assert int(arr[2 * batch - 1].max()) == 2 * batch
    assert int(arr[2 * batch : 3 * batch].max()) == 0
    assert int(arr[3 * batch].min()) == 3 * batch + 1
