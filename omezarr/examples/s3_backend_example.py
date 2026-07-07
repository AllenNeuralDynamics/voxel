"""Example: writing OME-Zarr to S3 with the streaming writer.

The writer takes a `Storage` describing *where* to write and *how* to reach it: `DirectS3`
writes arrays straight to S3, `StagedS3` stages shards to a local scratch dir then uploads
them. The `S3Store` connection carries only routing (endpoint/region/profile) -- never
secrets: credentials come from the standard AWS chain (a named profile, an instance role,
or ambient env), which the underlying clients resolve natively.
"""

from pathlib import Path

import numpy as np
from cloudpathlib import S3Path

from ome_zarr_writer import (
    DirectS3,
    OMEZarrWriter,
    S3Store,
    ScaleLevel,
    StagedS3,
    Storage,
    UIVec3D,
    UVec3D,
    WriterConfig,
)
from ome_zarr_writer.array.ts import TSArrayReader


def write_volume(storage: Storage) -> None:
    """Stream a small volume to `storage` (local, direct-to-S3, or staged)."""
    z, y, x = 64, 512, 512
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=z, y=y, x=x),
        voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
        max_level=ScaleLevel.L3,
    )
    writer = OMEZarrWriter(cfg, storage, slots=3)
    for i in range(z):
        writer.add_frame(np.full((y, x), i + 1, dtype=np.uint16))
    writer.close()
    print(f"wrote {z} frames to {writer.target}")


def example_direct() -> None:
    """Write arrays straight to S3, credentials from the ambient AWS chain (empty `S3Store`)."""
    write_volume(DirectS3(target=S3Path("s3://my-bucket/experiments/2024.ome.zarr"), store=S3Store()))


def example_profile() -> None:
    """Select a named ~/.aws profile and region for the connection."""
    store = S3Store(region="us-east-1", profile="my-profile")
    write_volume(DirectS3(target=S3Path("s3://my-bucket/experiment_002.ome.zarr"), store=store))


def example_minio_staged() -> None:
    """S3-compatible endpoint (MinIO / Vast) with local staging before upload."""
    store = S3Store(endpoint="http://localhost:9000", region="us-east-1")
    target = S3Path("s3://my-bucket/minio_experiment.ome.zarr")
    write_volume(StagedS3(scratch=Path("/tmp/ozw-scratch"), target=target, store=store))


def example_read(target: S3Path, store: S3Store) -> np.ndarray:
    """Read a written dataset's L0 back, reaching S3 via the same `S3Store` connection."""
    return TSArrayReader(target / "0", store).read_3d(z0=0, n=8)


if __name__ == "__main__":
    print("S3 write examples (need real buckets/credentials to run):")
    print("  example_direct()               -- arrays straight to S3, ambient AWS chain")
    print("  example_profile()              -- named ~/.aws profile + region")
    print("  example_minio_staged()         -- S3-compatible endpoint + local staging")
    print("  example_read(target, store)    -- read L0 back via TSArrayReader(store)")
