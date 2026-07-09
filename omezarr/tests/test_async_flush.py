"""Async-flush correctness for both writers.

Each flushes a batch to storage on a background pool as its downsample completes, and a slot may be
reassigned only after its flush has finished reading it (the FLUSHING → IDLE ``release()``). Driving a
ring with fewer slots than batches forces the ring to *wrap*, exercising that reuse path; distinct
per-frame values mean any reuse-before-flush would corrupt the read-back, so a green round-trip proves
the invariant holds while flush overlaps capture.
"""

from pathlib import Path

import numpy as np
import pytest
from vxlib.vec import UIVec3D, UVec3D

from ome_zarr_writer import Local, OMEZarrWriter, ScaleLevel, WriterConfig
from ome_zarr_writer.array.ts import TSArrayReader


def _read_l0(base: Path, z: int) -> np.ndarray:
    return TSArrayReader(Path(f"{base}.ome.zarr") / "0").read_3d(z0=0, n=z)


@pytest.mark.slow
def test_OMEZarrWriter_async_flush_wrapping_ring_roundtrip(tmp_path: Path) -> None:
    """OMEZarrWriter DatasetWriter (via the coordinator): same wrapping-ring invariant."""
    z, y, x = 256, 64, 64
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=z, y=y, x=x), voxel_size=UVec3D(z=1.0, y=0.5, x=0.5), max_level=ScaleLevel.L6
    )
    assert cfg.batch_z == 64 and z // cfg.batch_z == 4
    writer = OMEZarrWriter(slots=2)  # BatchSlot (process) — worker does downsample + write off the main GIL
    writer.begin_stack(cfg, Local(target=tmp_path / "v2"))
    for i in range(z):
        writer.add_frame(np.full((y, x), i + 1, dtype=np.uint16))
    writer.end_stack()
    writer.close()

    arr = _read_l0(tmp_path / "v2", z)
    assert arr.shape == (z, y, x)
    for i in range(z):
        assert int(arr[i].min()) == i + 1 and int(arr[i].max()) == i + 1, f"frame {i} corrupted"


@pytest.mark.slow
def test_OMEZarrWriter_reuses_ring_across_stacks(tmp_path: Path) -> None:
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
            writer.add_frame(np.full((y, x), base + i, dtype=np.uint16))
        writer.end_stack()
    writer.close()

    for stack, base in (("a", 1), ("b", 1000)):
        arr = _read_l0(tmp_path / stack, z)
        assert int(arr[0].max()) == base and int(arr[z - 1].max()) == base + z - 1, stack
