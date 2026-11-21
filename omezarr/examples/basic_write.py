"""Example: a basic streaming acquisition to a local OME-Zarr.

Writes a small volume frame-by-frame through `OMEZarrWriter`, then reads level 0
back with `TSArrayReader` and checks the per-frame content.
"""

import tempfile
from pathlib import Path

from ome_zarr_writer import Local, OMEZarrWriter, ScaleLevel, WriterConfig
from ome_zarr_writer.array.ts import TSArrayReader
from ome_zarr_writer.writer import _as_ome_zarr
from vxlib.vector import Transform, Vec3D


def main(directory: Path | None = None, filename: str = "stack") -> None:
    z, y, x = 256, 4096, 4096
    directory = Path(tempfile.mkdtemp()) if directory is None else directory
    storage = Local(target=directory / filename)  # the writer appends the .ome.zarr suffix

    cfg = WriterConfig(
        transform=Transform.grid((z, y, x), Vec3D(z=1.0, y=0.5, x=0.5)),
        max_level=ScaleLevel.L7,
        target_shard_gb=1,  # tiny shards keep the example small
    )

    # Batch depth (cfg.rounded_batch_frames) is policy-derived from the config knobs; RAM only sizes the ring slots.
    writer = OMEZarrWriter(slots=3)
    writer.open_dataset(cfg, storage)
    for i in range(z):
        with writer.new_frame() as frame:
            frame.fill(i + 1)  # frame i holds value i+1
    writer.release()

    dataset = _as_ome_zarr(storage.target)  # the writer holds no dataset after release(); derive it from the storage
    l0 = TSArrayReader(dataset / "0").read_3d(z0=0, z1=z)
    assert l0.shape == (z, y, x), l0.shape
    assert int(l0[0].max()) == 1
    assert int(l0[z - 1].max()) == z
    print(f"wrote + verified {z} frames at {dataset}")


if __name__ == "__main__":
    from datetime import datetime

    main(directory=Path(__file__).parent / "tmp", filename=datetime.now().astimezone().strftime("%Y%m%d_%H%M%S"))
