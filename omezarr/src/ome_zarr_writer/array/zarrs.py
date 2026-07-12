"""zarr-python + zarrs (Rust codec pipeline) backend for one Zarr v3 array.

Path-based: `open(target)` takes the array's full path -- a local `Path` (written through zarr's
`LocalStore`) or a cloudpathlib `S3Path` (written through obstore's `S3Store` behind zarr's
`ObjectStore`). Opens an existing array; its metadata must already have been written upstream.

S3 caveat -- config must go through the environment. The zarrs Rust pipeline reconstructs its own
object-store from the zarr store, and it only accepts an S3 connection configured via `AWS_*`
environment variables: passing endpoint/region as obstore ``S3Store`` kwargs or a ``config=`` dict
makes that reconstruction panic (``Expected config prefix to start with aws_``). So `open` writes
the connection into scoped `AWS_*` env (via `_apply_s3_env`) before constructing the store. Each
writer runs in its own single-store worker process, so this env scoping is contained; `open` clears
the connection keys first so a reused worker can't carry stale endpoint config across stores.

Side effect: importing this module enables the zarrs Rust codec pipeline globally via
`zarr.config.set(...)`. All subsequent zarr-python operations in the process use the zarrs pipeline.
"""

import os
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import zarr
import zarrs  # noqa: F401 — registers the zarrs codec pipeline
from cloudpathlib import S3Path
from vxlib import AnonymousCredentials, ProfileCredentials
from zarr.storage import LocalStore, ObjectStore

from ome_zarr_writer.storage import S3Store

from .base import ArrayWriter

# zarrs reconstructs its own Rust object-store from the zarr store and warns that connection pooling
# isn't shared across store instances — benign for our per-shard write pattern; silence the per-write noise.
warnings.filterwarnings("ignore", message="Successfully reconstructed a store", category=RuntimeWarning)

zarr.config.set(
    {
        "threading.max_workers": None,
        "array.write_empty_chunks": False,
        "codec_pipeline": {
            "path": "zarrs.ZarrsCodecPipeline",
            "validate_checksums": True,
            "chunk_concurrent_maximum": None,
            "chunk_concurrent_minimum": 4,
            "direct_io": False,
            "batch_size": 1,  # consumed only by the pure-Python fallback pipeline; native path ignores it
        },
    }
)

# S3 connection keys this backend sets from the store; cleared on each open so a reused worker never
# carries a previous store's endpoint/anon config forward. Credentials are handled separately below.
_S3_CONN_ENV = ("AWS_ENDPOINT_URL", "AWS_ALLOW_HTTP", "AWS_VIRTUAL_HOSTED_STYLE_REQUEST", "AWS_SKIP_SIGNATURE")

# Threads for the per-shard write in `write_slice` (each shard write hits zarrs' fast single-shard codec
# path; the default multi-shard write serializes inner-chunk encoding). Env-tunable so the S3 concurrency
# can be swept without a code edit (higher may raise S3 upload throughput toward the endpoint ceiling).
_SHARD_WRITE_WORKERS = int(os.environ.get("VOXEL_ZARRS_SHARD_WORKERS", "16"))


def _apply_s3_env(store: S3Store) -> None:
    """Write `store`'s S3 connection into `AWS_*` env — the only form the zarrs Rust pipeline accepts
    (kwargs/config-dict trigger a Rust panic). Endpoint/region/http from the store; credentials from
    the strategy: anonymous -> unsigned; profile -> resolved to concrete keys via botocore (obstore's
    env provider does not read `AWS_PROFILE`); env/chain -> left to obstore's ambient `AWS_*` lookup."""
    for key in _S3_CONN_ENV:
        os.environ.pop(key, None)
    if store.region:
        os.environ["AWS_REGION"] = store.region
    if store.endpoint:
        os.environ["AWS_ENDPOINT_URL"] = store.endpoint
        os.environ["AWS_VIRTUAL_HOSTED_STYLE_REQUEST"] = "false"  # path-style for a custom endpoint
        if store.endpoint.startswith("http://"):
            os.environ["AWS_ALLOW_HTTP"] = "true"
    creds = store.credentials
    if isinstance(creds, AnonymousCredentials):
        os.environ["AWS_SKIP_SIGNATURE"] = "true"
    elif isinstance(creds, ProfileCredentials):
        import botocore.session

        session = botocore.session.Session(profile=creds.name)
        if creds.config_file is not None:
            session.set_config_variable("config_file", str(creds.config_file))
        if creds.credentials_file is not None:
            session.set_config_variable("credentials_file", str(creds.credentials_file))
        resolved = session.get_credentials()
        if resolved is None:
            raise RuntimeError(f"could not resolve AWS credentials for profile {creds.name!r}")
        frozen = resolved.get_frozen_credentials()
        os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
        if frozen.token:
            os.environ["AWS_SESSION_TOKEN"] = frozen.token


class ZarrsArrayWriter(ArrayWriter):
    """zarr-python writer using the zarrs Rust codec pipeline. Opens an existing Zarr v3 array at
    `target` (metadata expected to be present): a local `Path` via `LocalStore`, or an `S3Path` via
    obstore `S3Store` behind zarr's `ObjectStore` (see the module docstring on the `AWS_*`-env S3 path)."""

    def __init__(self) -> None:
        self._handle: Any = None

    def open(self, target: Path | S3Path, store: S3Store | None = None) -> None:
        if isinstance(target, S3Path):
            if store is None:
                raise ValueError("ZarrsArrayWriter requires an S3Store for an S3 target")
            from obstore.store import S3Store as ObstoreS3Store

            _apply_s3_env(store)
            obs = ObstoreS3Store(bucket=target.bucket, prefix=target.key)  # config read from AWS_* env
            self._handle = zarr.open_array(store=ObjectStore(obs, read_only=False), mode="r+")
            return
        del store  # local target: no S3 connection to apply
        local_store = LocalStore(target.expanduser().resolve().as_posix())
        self._handle = zarr.open_array(store=local_store, mode="r+")

    def write_slice(self, c: int, z_offset: int, arr: np.ndarray) -> int:
        if self._handle is None:
            raise RuntimeError("write_slice called before open")
        z_end = z_offset + arr.shape[0]
        shards = getattr(self._handle, "shards", None)
        if not shards:  # unsharded array: a single write is already the fast path
            self._handle[c, z_offset:z_end, :, :] = arr
            return int(arr.nbytes)
        # Sharded: write one shard-region at a time, concurrently. zarrs-python's *multi-shard* write
        # path serializes inner-chunk encoding (~4x slower measured); a write covering a *single* shard
        # gets full codec/inner-chunk parallelism. Tiling the slab into per-shard writes (each aligned
        # to a shard, so no read-modify-write) and running them on a thread pool recovers the speed.
        sz, sy, sx = shards[-3], shards[-2], shards[-1]
        y_dim, x_dim = self._handle.shape[-2], self._handle.shape[-1]
        tiles = [
            (z, y, x) for z in range(z_offset, z_end, sz) for y in range(0, y_dim, sy) for x in range(0, x_dim, sx)
        ]

        def _write_shard(t: tuple[int, int, int]) -> None:
            z, y, x = t
            ze, ye, xe = min(z + sz, z_end), min(y + sy, y_dim), min(x + sx, x_dim)
            self._handle[c, z:ze, y:ye, x:xe] = arr[z - z_offset : ze - z_offset, y:ye, x:xe]

        with ThreadPoolExecutor(max_workers=min(_SHARD_WRITE_WORKERS, len(tiles))) as pool:
            for _ in pool.map(_write_shard, tiles):  # consume the iterator to surface any exception
                pass
        return int(arr.nbytes)

    def close(self) -> None:
        self._handle = None
