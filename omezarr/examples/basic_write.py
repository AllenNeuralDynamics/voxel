"""Example: a basic streaming acquisition to a local OME-Zarr.

Writes a small volume frame-by-frame through `OMEZarrWriter`, then reads level 0
back with `TSArrayReader` and checks the per-frame content.
"""

import tempfile
from pathlib import Path

import numpy as np

from ome_zarr_writer import Local, OMEZarrWriter, PyramidRingBuffer, ScaleLevel, UIVec3D, UVec3D, WriterConfig
from ome_zarr_writer.array.ts import TSArrayReader


def main(directory: Path | None = None, filename: str = "stack") -> None:
    z, y, x = 256, 4096, 4096
    directory = Path(tempfile.mkdtemp()) if directory is None else directory
    storage = Local(target=directory / filename)  # the writer appends the .ome.zarr suffix

    cfg = WriterConfig(
        volume_shape=UIVec3D(z=z, y=y, x=x),
        voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
        max_level=ScaleLevel.L7,
        target_shard_gb=1,  # tiny shards keep the example small
    )

    # Batch depth (cfg.batch_z) is policy-derived from the config knobs; RAM only sizes the ring slots.
    writer = OMEZarrWriter(cfg, storage, ring_buffer=PyramidRingBuffer.PROCESS, slots=3)
    for i in range(z):
        writer.add_frame(np.full((y, x), i + 1, dtype=np.uint16))  # frame i holds value i+1
    writer.close()

    l0 = TSArrayReader(writer.target / "0").read_3d(z0=0, z1=z)
    assert l0.shape == (z, y, x), l0.shape
    assert int(l0[0].max()) == 1 and int(l0[z - 1].max()) == z
    print(f"wrote + verified {z} frames at {writer.target}")


if __name__ == "__main__":
    from datetime import datetime

    main(directory=Path(__file__).parent / "tmp", filename=datetime.now().strftime("%Y%m%d_%H%M%S"))
