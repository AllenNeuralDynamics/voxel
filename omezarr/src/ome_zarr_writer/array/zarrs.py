"""zarr-python + zarrs (Rust codec pipeline) backend for one Zarr v3 array.

Path-based: `open(target)` takes the array's full local `Path`. Filesystem only --
raises on a cloudpathlib `S3Path`, since the zarrs `LocalStore` pipeline has no S3
backend here (use the TensorStore backend for remote targets). Opens an existing
array; its metadata must already have been written upstream.

Side effect: importing this module enables the zarrs Rust codec pipeline globally
via `zarr.config.set(...)`. All subsequent zarr-python operations in the process
use the zarrs pipeline.
"""

from pathlib import Path
from typing import Any

import numpy as np
import zarr
import zarrs  # noqa: F401 — registers the zarrs codec pipeline
from cloudpathlib import S3Path
from zarr.storage import LocalStore

from .base import ArrayWriter

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
        },
    }
)


class ZarrsArrayWriter(ArrayWriter):
    """zarr-python writer using the zarrs Rust codec pipeline.

    Local filesystem only. Opens an existing Zarr v3 array at `target`; the
    metadata is expected to already be there.
    """

    def __init__(self) -> None:
        self._handle: Any = None

    def open(self, target: Path | S3Path) -> None:
        if isinstance(target, S3Path):
            raise ValueError("ZarrsArrayWriter is filesystem-only; use the TensorStore backend for S3 targets")
        store = LocalStore(target.expanduser().resolve().as_posix())
        self._handle = zarr.open_array(store=store, mode="r+")

    def write_slice(self, c: int, z_offset: int, arr: np.ndarray) -> int:
        if self._handle is None:
            raise RuntimeError("write_slice called before open")
        z_end = z_offset + arr.shape[0]
        self._handle[c, z_offset:z_end, :, :] = arr
        return int(arr.nbytes)

    def close(self) -> None:
        self._handle = None
