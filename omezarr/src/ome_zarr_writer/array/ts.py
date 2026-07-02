"""TensorStore-backed `ArrayWriter` for one Zarr v3 array.

Path-based: `open(target)` takes the array's full path -- a local `Path` (FileKvStore)
or a cloudpathlib `S3Path` (S3KvStore). S3 credentials, region, and endpoint come from
the environment (the AWS chain / `AWS_*` vars), so no auth is threaded through here.

NOTE (option "b"): if env-supplied connection ever proves insufficient (e.g. a MinIO
endpoint TensorStore won't pick up from the environment), the connection settings could
be carried on the writer-level config and applied to the S3 kvstore spec here.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pydantic_tensorstore as pts
import tensorstore as ts
from cloudpathlib import S3Path

from .base import ArrayWriter


class TSArrayWriter(ArrayWriter):
    """TensorStore writer for one Zarr v3 array. Opens an existing array -- its metadata
    must already have been written at `target`."""

    def __init__(self) -> None:
        self._handle: Any = None

    def open(self, target: Path | S3Path) -> None:
        self._handle = ts.open(
            {
                "driver": "zarr3",
                "kvstore": _kvstore_for(target),
                "open": True,
                "create": False,
            }
        ).result()

    def write_slice(self, c: int, z_offset: int, arr: np.ndarray) -> int:
        if self._handle is None:
            raise RuntimeError("write_slice called before open")
        z_end = z_offset + arr.shape[0]
        self._handle[c, z_offset:z_end, :, :].write(arr).result()
        return int(arr.nbytes)

    def close(self) -> None:
        self._handle = None


def _kvstore_for(target: Path | S3Path) -> dict[str, Any]:
    """TensorStore kvstore spec for the array at `target`. S3 credentials / region /
    endpoint are resolved by TensorStore from the environment."""
    if isinstance(target, S3Path):
        spec = pts.S3KvStore(bucket=target.bucket, path=target.key)
    else:
        spec = pts.FileKvStore(path=target.expanduser().resolve().as_posix())
    return spec.model_dump(exclude_none=True, mode="json")
