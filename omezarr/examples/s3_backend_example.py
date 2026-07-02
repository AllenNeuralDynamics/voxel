"""Example: writing OME-Zarr to S3 with the streaming writer.

S3 connection settings come from the *environment* (the AWS credential chain) -- the
writer and its s5cmd uploads don't take an `S3Auth`. To use specific credentials, set
the environment yourself, or build an `S3Auth` and call `.apply_env()` (the reader's
auth model bridged onto the env-driven writer). Reads can pass an explicit `S3Auth`
directly, which is the only way to express cases the environment can't -- e.g. an
anonymous public bucket.
"""

from pathlib import Path

import numpy as np
from cloudpathlib import S3Path

from ome_zarr_writer import OMEZarrWriter, ScaleLevel, UIVec3D, UVec3D, WriterConfig
from ome_zarr_writer.viewer.loader import S3Auth, S3AuthType, ZarrLoader


def write_to_s3(target: S3Path, scratch: Path | None = None) -> None:
    """Stream a small volume to an S3 OME-Zarr at `target` (env-driven auth). Pass
    `scratch` (a local dir) to stage shards locally and upload them per batch."""
    z, y, x = 64, 512, 512
    cfg = WriterConfig(
        volume_shape=UIVec3D(z=z, y=y, x=x),
        voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
        max_level=ScaleLevel.L3,
        target=target,
        scratch=scratch,
    )
    writer = OMEZarrWriter(cfg, slots=3)
    for i in range(z):
        writer.add_frame(np.full((y, x), i + 1, dtype=np.uint16))
    writer.close()
    print(f"wrote {z} frames to {target.as_uri()}")


def example_env_chain() -> None:
    """Default: credentials from the ambient AWS chain (env vars / instance role / profile)."""
    write_to_s3(S3Path("s3://my-bucket/experiments/2024.ome.zarr"))


def example_access_key() -> None:
    """Explicit access key -> environment -> writer, via `S3Auth.apply_env()`."""
    S3Auth(
        auth_type=S3AuthType.ACCESS_KEY,
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
    ).apply_env()
    write_to_s3(S3Path("s3://my-bucket/experiment_002.ome.zarr"))


def example_profile() -> None:
    """A named AWS profile -> environment -> writer."""
    S3Auth(auth_type=S3AuthType.PROFILE, profile="my-profile", region="us-east-1").apply_env()
    write_to_s3(S3Path("s3://my-bucket/experiment_003.ome.zarr"))


def example_minio_staged() -> None:
    """S3-compatible endpoint (MinIO/Wasabi) with local staging before upload."""
    S3Auth(
        auth_type=S3AuthType.ACCESS_KEY,
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
        endpoint="http://localhost:9000",
        region="us-east-1",
    ).apply_env()
    write_to_s3(S3Path("s3://my-bucket/minio_experiment.ome.zarr"), scratch=Path("/tmp/ozw-scratch"))


def example_read_anonymous(target: S3Path) -> np.ndarray:
    """Anonymous read of a public bucket -- the environment can't express this, so pass
    an explicit `S3Auth` to the reader instead."""
    return ZarrLoader(target / "0", auth=S3Auth(auth_type=S3AuthType.ANONYMOUS)).get_3d(z0=0, n=8)


if __name__ == "__main__":
    print("S3 write examples (need real buckets/credentials to run):")
    print("  example_env_chain()      -- ambient AWS chain (env / instance role / profile)")
    print("  example_access_key()     -- explicit key via S3Auth.apply_env()")
    print("  example_profile()        -- named profile via S3Auth.apply_env()")
    print("  example_minio_staged()   -- S3-compatible endpoint + local staging")
    print("  example_read_anonymous(target) -- anonymous public read via ZarrLoader(auth=...)")
