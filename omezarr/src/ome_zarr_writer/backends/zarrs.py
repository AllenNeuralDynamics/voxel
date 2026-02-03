from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numcodecs
import numpy as np
import zarr
import zarrs  # noqa: F401
from zarr.storage import LocalStore

from ome_zarr_writer.backends.base import Backend
from ome_zarr_writer.buffer import MultiScaleBuffer
from ome_zarr_writer.types import Compression, ScaleLevel

# Enable Zarrs pipeline globally
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


class ZarrsBackend(Backend):
    """
    Zarrs-based backend for multi-scale Zarr v3 arrays.

    Writes each scale level to a separate LocalStore-backed Zarr array
    using zarrs' high-performance Rust codec pipeline.

    Features:
    - Parallel writes across scale levels
    - Pre-initialized arrays for predictable structure
    - Configurable Blosc or GZip compression (optimized for uint16)
    """

    _arrays: dict[ScaleLevel, zarr.Array] = {}
    _batch_count: int = 0
    _executor: ThreadPoolExecutor

    def _initialize(self) -> None:
        """Create or open all Zarr arrays for each scale level."""
        self._executor = ThreadPoolExecutor(max_workers=8)
        self._batch_count = 0
        assert isinstance(self.storage_root, Path), "ZarrsBackend requires a local path"
        root = self.storage_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)

        for level in self.cfg.max_level.levels:
            path = root / level.name
            path.mkdir(exist_ok=True)

            scaled_shape = level.scale(self.cfg.volume_shape)
            scaled_shard = level.scale(self.cfg.shard_shape)

            compressor = None
            if self.cfg.compression == Compression.BLOSC_ZSTD:
                compressor = numcodecs.Blosc(
                    cname="zstd",
                    clevel=3,
                    shuffle=2,  # bitshuffle
                    typesize=2,  # uint16
                )
            elif self.cfg.compression == Compression.BLOSC_LZ4:
                compressor = numcodecs.Blosc(
                    cname="lz4",
                    clevel=3,
                    shuffle=2,  # bitshuffle
                    typesize=2,  # uint16
                )
            elif self.cfg.compression == Compression.GZIP:
                compressor = numcodecs.GZip(level=1)
            elif self.cfg.compression == Compression.NONE:
                compressor = None
            else:
                raise ValueError(f"Unsupported compression: {self.cfg.compression}")

            store = LocalStore(str(path))
            arr = zarr.create(
                store=store,
                shape=(scaled_shape.z, scaled_shape.y, scaled_shape.x),
                chunks=(scaled_shard.z, scaled_shard.y, scaled_shard.x),
                dtype=np.uint16,
                compressor=compressor,
                overwrite=True,
            )
            self._arrays[level] = arr

    def write_batch(self, buffer: MultiScaleBuffer) -> bool:
        """
        Write a complete MultiScaleBuffer batch to Zarrs arrays.

        Args:
            buffer: MultiScaleBuffer ready for storage (all scales computed)

        Returns:
            True if all scale writes succeed, False otherwise
        """
        if buffer.batch_idx is None:
            raise ValueError("Buffer must have a batch_idx assigned")

        z_start, z_end = self.cfg.get_batch_z_range(buffer.batch_idx)

        futures = []
        for level, arr in self._arrays.items():
            data = buffer.get_volume(level)
            futures.append(self._executor.submit(self._write_scale_block, arr, level, data, z_start, z_end))

        results = [f.result() for f in futures]
        ok = all(results)
        if ok:
            self._batch_count += 1
        return ok

    def _write_scale_block(self, arr: zarr.Array, level: ScaleLevel, data: np.ndarray, z0: int, z1: int) -> bool:
        """Write one scale level’s z-slice block into its Zarr array."""
        try:
            z_start_scaled = z0 // level.factor
            z_end_scaled = z1 // level.factor
            slice_shape = z_end_scaled - z_start_scaled

            arr[z_start_scaled:z_end_scaled, :, :] = data[:slice_shape, :, :]
            return True
        except Exception as e:
            print(f"[ZarrsBackend] Error writing {level.name}: {e}")
            return False

    def _finalize(self) -> None:
        """Shut down executors and close resources."""
        self._executor.shutdown(wait=True)
        self._arrays.clear()
