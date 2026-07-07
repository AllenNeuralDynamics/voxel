"""TensorStore-backed array I/O for one Zarr array.

Path-based: takes the array's full path -- a local `Path` (FileKvStore) or a cloudpathlib
`S3Path` (S3KvStore). For an S3 target the `S3Store` supplies the endpoint, region, and credential
strategy; the endpoint must be passed in the spec here because TensorStore cannot read it from the
environment.

`TSArrayWriter` writes an existing array (metadata pre-written); `TSArrayReader` opens one and
reads 3D slices.
"""

from pathlib import Path
from typing import Any, assert_never

import numpy as np
import pydantic_tensorstore as pts
import tensorstore as ts
from cloudpathlib import S3Path
from vxlib import AnonymousCredentials, ChainCredentials, EnvCredentials, ProfileCredentials, S3Credentials, S3Store

from .base import ArrayWriter


class TSArrayWriter(ArrayWriter):
    """TensorStore writer for one Zarr v3 array. Opens an existing array -- its metadata
    must already have been written at `target`."""

    def __init__(self) -> None:
        self._handle: Any = None

    def open(self, target: Path | S3Path, store: S3Store | None = None) -> None:
        self._handle = ts.open(
            {
                "driver": "zarr3",
                "kvstore": _kvstore_for(target, store),
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


class TSArrayReader:
    """TensorStore reader for one Zarr array — the read-side mirror of `TSArrayWriter`. Opens an
    existing array at `target` once, then reads 3D slices; for an S3 target, `store` supplies
    endpoint/region/credentials (same as the writer), or pass `anonymous=True` for a public bucket."""

    def __init__(
        self, target: Path | S3Path, store: S3Store | None = None, *, anonymous: bool = False, v3: bool = True
    ) -> None:
        driver = "zarr3" if v3 else "zarr"
        self._handle: Any = ts.open(
            {
                "driver": driver,
                "kvstore": _kvstore_for(target, store, anonymous=anonymous),
                "open": True,
                "create": False,
            }
        ).result()

    @property
    def rank(self) -> int:
        return int(self._handle.rank)

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(int(x) for x in self._handle.shape)

    def read_3d(self, z0: int = 0, n: int | None = None, z1: int | None = None) -> np.ndarray:
        """Read a 3D (z, y, x) slice; leading axes (e.g. channel) are taken at index 0. `z1`
        (exclusive) overrides `n`; otherwise the range is [z0, z0 + (n or 128))."""
        if z1 is None:
            z1 = z0 + (n if n is not None else 128)
        leading = (0,) * (self._handle.rank - 3)
        return np.array(self._handle[(*leading, slice(z0, z1), slice(None), slice(None))])


def _aws_credentials_spec(creds: S3Credentials) -> dict[str, Any]:
    """TensorStore ``aws_credentials`` spec for a credential strategy. Naming one provider keeps
    TensorStore from constructing (and noisily logging the init of) the full default chain."""
    match creds:
        case EnvCredentials():
            return {"type": "environment"}
        case ProfileCredentials():
            spec: dict[str, Any] = {"type": "profile", "profile": creds.name}
            if creds.config_file is not None:
                spec["config_file"] = str(creds.config_file)
            if creds.credentials_file is not None:
                spec["credentials_file"] = str(creds.credentials_file)
            return spec
        case ChainCredentials():
            return {"type": "default"}
        case AnonymousCredentials():
            return {"type": "anonymous"}
        case _:
            assert_never(creds)


def _kvstore_for(target: Path | S3Path, store: S3Store | None, *, anonymous: bool = False) -> dict[str, Any]:
    """TensorStore kvstore spec for the array at `target`. For an S3 target, `store` supplies the
    endpoint, region, and credential strategy; `anonymous` forces unsigned access (a public bucket),
    overriding the store's strategy."""
    if not isinstance(target, S3Path):
        spec = pts.FileKvStore(path=target.expanduser().resolve().as_posix())
        return spec.model_dump(exclude_none=True, mode="json")
    credentials: dict[str, Any] | None = None
    if anonymous:
        credentials = {"type": "anonymous"}
    elif store is not None:
        credentials = _aws_credentials_spec(store.credentials)
    spec = pts.S3KvStore(
        bucket=target.bucket,
        path=target.key,
        endpoint=store.endpoint if store else None,
        aws_region=store.region if store else None,
        aws_credentials=credentials,
    )
    return spec.model_dump(exclude_none=True, mode="json")
