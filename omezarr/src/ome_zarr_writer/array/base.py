"""The `ArrayWriter` abstraction used by the Writer.

`ArrayWriter` writes one Zarr v3 array to a path — a local `pathlib.Path` or a
cloudpathlib `S3Path`. Targets are addressed purely by path: joining segments,
splitting bucket/key, and URI rendering live on the path types themselves, and
S3 credentials / region / endpoint come from the environment (the AWS chain),
so no auth is threaded through here.

`ArrayWriter.Backend` is a `StrEnum` that doubles as a factory: calling a
member (e.g. `ArrayWriter.Backend.TS()`) constructs the matching backend.
"""

from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path

import numpy as np
from cloudpathlib import S3Path


class ArrayWriter(ABC):
    """Writes one Zarr v3 array. Library-specific; no pyramid awareness.

    Lifecycle: `open(target)` once → `write_slice(c, z_offset, arr)` N times →
    `close()` once. Multi-array (e.g., multi-scale) workflows compose multiple
    `ArrayWriter` instances at a higher layer, one per array path.
    """

    class Backend(StrEnum):
        TS = "tensorstore"
        AQZ = "acquire"
        ZARRS = "zarrs"

        def __call__(self) -> "ArrayWriter":
            if self is ArrayWriter.Backend.TS:
                from .ts import TSArrayWriter

                return TSArrayWriter()
            if self is ArrayWriter.Backend.ZARRS:
                from .zarrs import ZarrsArrayWriter

                return ZarrsArrayWriter()
            raise ValueError(f"Unsupported ArrayWriter.Backend: {self}")

    @abstractmethod
    def open(self, target: Path | S3Path) -> None:
        """Open the array at `target`. Metadata must already
        exist there (the caller writes it before calling `open`)."""

    @abstractmethod
    def write_slice(self, c: int, z_offset: int, arr: np.ndarray) -> int:
        """Write `arr` (shape `[z, y, x]`) at channel `c`, z-range
        [z_offset, z_offset + arr.shape[0]). Synchronous: blocks until
        durable. Returns bytes written. Raises on error."""

    @abstractmethod
    def close(self) -> None:
        """Drain pending writes and release the handle."""
