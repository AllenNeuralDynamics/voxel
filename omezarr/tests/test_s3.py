"""End-to-end S3 round-trip against a throwaway MinIO container (the `minio` fixture, conftest.py).

Proves the `S3Store` connection is threaded to every client: `DirectS3` exercises TensorStore
writing arrays straight to S3 plus cloudpathlib writing metadata; `StagedS3` exercises the s5cmd
upload of locally-staged shards. MinIO is an S3-compatible endpoint indistinguishable to the
writer from a real one (Vast, AWS), so a green run here validates the whole path.

Marked `slow` — excluded from pre-push, run in CI; skips when Docker is unavailable (see conftest).
"""

from pathlib import Path

import numpy as np
import pytest
from cloudpathlib import S3Path

from ome_zarr_writer import (
    DirectS3,
    OMEZarrWriter,
    ScaleLevel,
    StagedS3,
    Storage,
    UIVec3D,
    UVec3D,
    WriterConfig,
)
from ome_zarr_writer.array.ts import TSArrayReader

from conftest import Minio

pytestmark = pytest.mark.slow


def _storage(kind: str, tmp_path: Path, minio: Minio) -> Storage:
    target = S3Path(f"s3://{minio.bucket}/{kind}")
    if kind == "staged":
        return StagedS3(scratch=tmp_path / "scratch", target=target, store=minio.store())
    return DirectS3(target=target, store=minio.store())


@pytest.mark.parametrize("kind", ["direct", "staged"])
def test_s3_roundtrip(minio: Minio, kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Writer clients resolve credentials from the ambient chain; endpoint/region come from the store.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", minio.user)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", minio.password)
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    # L6 (factor 64) aligns batch_z to the z-shard so each staged batch is a complete shard;
    # z=128 gives two batches, exercising the per-batch upload loop.
    z, y, x = 128, 128, 128
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=z, y=y, x=x), voxel_size=UVec3D(z=1.0, y=0.5, x=0.5), max_level=ScaleLevel.L6
    )
    writer = OMEZarrWriter(slots=3)
    writer.begin_stack(cfg, _storage(kind, tmp_path, minio))
    for i in range(z):
        writer.add_frame(np.full((y, x), i + 1, dtype=np.uint16))
    writer.close()

    # Objects landed in S3: group + level metadata and L0 shards.
    keys = [
        o["Key"]
        for o in minio.client().list_objects_v2(Bucket=minio.bucket, Prefix=f"{kind}.ome.zarr/").get("Contents", [])
    ]
    assert f"{kind}.ome.zarr/zarr.json" in keys, keys
    assert any(k.startswith(f"{kind}.ome.zarr/0/") for k in keys), keys

    # Bytes are real: read L0 back (same store connection, creds from the env above) and check
    # the per-frame values survived the round-trip.
    arr = TSArrayReader(S3Path(f"s3://{minio.bucket}/{kind}.ome.zarr/0"), minio.store()).read_3d(z0=0, n=z)
    assert arr.shape == (z, y, x)
    assert int(arr[0].max()) == 1
    assert int(arr[z - 1].max()) == z
