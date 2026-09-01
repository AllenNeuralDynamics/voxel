"""Async-flush correctness for both writers.

Each flushes a batch to storage on a background pool as its downsample completes, and a slot may be
reassigned only after its flush has finished reading it (the FLUSHING → IDLE ``release()``). Driving a
ring with fewer slots than batches forces the ring to *wrap*, exercising that reuse path; distinct
per-frame values mean any reuse-before-flush would corrupt the read-back, so a green round-trip proves
the invariant holds while flush overlaps capture.
"""

from concurrent.futures import Future
from pathlib import Path

import numpy as np
import pytest
from ome_zarr_writer import Local, OMEZarrWriter, ScaleLevel, WriterConfig
from ome_zarr_writer.array.ts import TSArrayReader
from vxlib.vector import UIVec3D, UVec3D


def _read_l0(base: Path, z: int) -> np.ndarray:
    return TSArrayReader(Path(f"{base}.ome.zarr") / "0").read_3d(z0=0, n=z)


@pytest.mark.slow
def test_OMEZarrWriter_async_flush_wrapping_ring_roundtrip(tmp_path: Path) -> None:  # noqa: N802
    """OMEZarrWriter DatasetWriter (via the coordinator): same wrapping-ring invariant."""
    z, y, x = 256, 64, 64
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=z, y=y, x=x), voxel_size=UVec3D(z=1.0, y=0.5, x=0.5), max_level=ScaleLevel.L6
    )
    assert cfg.batch_z == 64
    assert z // cfg.batch_z == 4
    writer = OMEZarrWriter(slots=2)  # BatchSlot (process) — worker does downsample + write off the main GIL
    writer.begin_stack(cfg, Local(target=tmp_path / "v2"))
    for i in range(z):
        with writer.new_frame() as frame:
            frame.fill(i + 1)
    writer.end_stack()
    writer.close()

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
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=z, y=y, x=x), voxel_size=UVec3D(z=1.0, y=0.5, x=0.5), max_level=ScaleLevel.L6
    )
    writer = OMEZarrWriter(slots=2)  # BatchSlot (process) — worker does downsample + write off the main GIL
    for stack, base in (("a", 1), ("b", 1000)):
        writer.begin_stack(cfg, Local(target=tmp_path / stack))
        for i in range(z):
            with writer.new_frame() as frame:
                frame.fill(base + i)
        writer.end_stack()
    writer.close()

    for stack, base in (("a", 1), ("b", 1000)):
        arr = _read_l0(tmp_path / stack, z)
        assert int(arr[0].max()) == base, stack
        assert int(arr[z - 1].max()) == base + z - 1, stack


@pytest.mark.slow
def test_frame_abort_does_not_advance(tmp_path: Path) -> None:
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=1, y=64, x=64),
        voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
        max_level=ScaleLevel.L0,
    )
    writer = OMEZarrWriter(slots=2)
    writer.begin_stack(cfg, Local(target=tmp_path / "abort"))
    with pytest.raises(ValueError, match="could not broadcast"), writer.new_frame() as abandoned:
        np.copyto(abandoned, np.empty(0, dtype=np.uint16))
    assert writer._ring is not None
    assert all(slot.reusable for slot in writer._ring)
    with writer.new_frame() as frame:
        frame.fill(7)
    writer.end_stack()
    writer.close()

    assert int(_read_l0(tmp_path / "abort", 1)[0].max()) == 7


@pytest.mark.slow
def test_retained_frame_prevents_slot_reuse_after_processing(tmp_path: Path) -> None:
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=1, y=64, x=64),
        voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
        max_level=ScaleLevel.L0,
    )
    writer = OMEZarrWriter(slots=2)
    writer.begin_stack(cfg, Local(target=tmp_path / "retained"))
    with writer.new_frame() as frame:
        frame.fill(11)
    lease = writer.latest_frame()
    writer.end_stack()

    assert writer._ring is not None
    retained_slot = next(slot for slot in writer._ring if slot.active_readers)
    assert retained_slot.stage.name == "IDLE"
    assert not retained_slot.reusable
    assert not lease.array.flags.writeable
    lease.close()
    assert retained_slot.reusable
    writer.close()


@pytest.mark.slow
def test_flush_failure_poisoning_is_sticky(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=1, y=64, x=64),
        voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
        max_level=ScaleLevel.L0,
    )
    writer = OMEZarrWriter(slots=2)
    dataset = writer.begin_stack(cfg, Local(target=tmp_path / "failed"))
    failed: Future[None] = Future()
    failed.set_exception(RuntimeError("flush failed"))
    monkeypatch.setattr(dataset._ring[0], "flush", lambda: failed)

    with writer.new_frame() as frame:
        frame.fill(1)
    lease = writer.latest_frame()
    with pytest.raises(RuntimeError, match="flush failed"):
        dataset.close()

    assert not dataset.ready_for_batch
    with pytest.raises(RuntimeError, match="cannot continue"), dataset.new_frame():
        pass
    with pytest.raises(RuntimeError, match="flush failed"):
        writer.end_stack()
    assert writer._ring is not None
    assert writer._ring_failed

    lease.close()
    writer.close()
