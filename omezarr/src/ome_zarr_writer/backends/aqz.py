"""
Acquire-Zarr backend for OME-Zarr streaming.

This backend uses acquire-zarr (https://github.com/acquire-project/acquire-zarr)
for high-performance Zarr v3 streaming with OME-NGFF metadata support.

Features:
- Native Zarr v3 streaming with c-blosc compression
- Optimized for microscopy acquisition workflows
- Parallel writes across scale levels
- Support for both filesystem and S3 storage

Installation:
    pip install acquire-zarr

Note on S3 Authentication:
    acquire-zarr requires AWS credentials to be configured via environment variables
    or AWS credentials file before importing the library:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_SESSION_TOKEN (optional, for temporary credentials)
"""

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import numpy as np

from ome_zarr_writer.backends.base import Backend
from ome_zarr_writer.buffer import MultiScaleBuffer
from ome_zarr_writer.types import Compression, ScaleLevel

if TYPE_CHECKING:
    from ome_zarr_writer.s3_utils import S3Config

try:
    import acquire_zarr as aqz
except ImportError as e:
    raise ImportError("acquire-zarr is required for AcquireZarrBackend. Install with: pip install acquire-zarr") from e


# Compression codec mapping
# Note: acquire-zarr uses c-blosc internally, so we map our compression
# types to appropriate blosc configurations
_COMPRESSION_MAP = {
    Compression.NONE: None,
    Compression.GZIP: "gzip",
    Compression.ZSTD: "zstd",
    Compression.LZ4: "lz4",
    Compression.BLOSC_LZ4: "lz4",  # acquire-zarr uses blosc by default
    Compression.BLOSC_ZSTD: "zstd",
}


def s3_settings_from_config(config: "S3Config") -> aqz.S3Settings:
    """
    Convert S3Config to acquire-zarr S3Settings.

    Note: acquire-zarr handles authentication via environment variables
    (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN) or
    AWS credentials file. These must be set before importing acquire-zarr.

    Args:
        config: S3Config instance

    Returns:
        aqz.S3Settings configured for the S3 endpoint

    Example:
        >>> from ome_zarr_writer.s3_utils import S3Config, S3AuthType
        >>> import os
        >>>
        >>> # Set credentials before importing acquire-zarr
        >>> os.environ['AWS_ACCESS_KEY_ID'] = 'your-key'
        >>> os.environ['AWS_SECRET_ACCESS_KEY'] = 'your-secret'
        >>>
        >>> config = S3Config(
        ...     bucket="my-bucket",
        ...     path="data",
        ...     auth_type=S3AuthType.ACCESS_KEY,
        ...     endpoint="s3.amazonaws.com",
        ...     region="us-east-1"
        ... )
        >>> s3_settings = s3_settings_from_config(config)
    """
    return aqz.S3Settings(
        endpoint=config.endpoint or "s3.amazonaws.com",
        bucket_name=config.bucket,
        region=config.region or "us-east-1",
    )


class AcquireZarrBackend(Backend):
    """
    Acquire-Zarr backend for streaming multi-scale Zarr v3 arrays.

    Creates separate ZarrStream instances for each scale level and writes
    batches in parallel for optimal performance.

    Features:
    - High-performance streaming via acquire-zarr
    - Parallel writes across pyramid levels
    - Native Zarr v3 with OME-NGFF metadata
    - Support for both local filesystem and S3 storage

    Examples:
        >>> from ome_zarr_writer.backends.aqz import AcquireZarrBackend
        >>> from ome_zarr_writer.config import WriterConfig
        >>> from vxlib.vec import UIVec3D
        >>> from ome_zarr_writer.types import ScaleLevel
        >>> from ome_zarr_writer.s3_utils import S3Config, S3AuthType
        >>> import os
        >>>
        >>> # Local filesystem storage
        >>> cfg = WriterConfig(
        ...     name="experiment",
        ...     volume_shape=UIVec3D(100, 512, 512),
        ...     shard_shape=UIVec3D(10, 128, 128),
        ...     chunk_shape=UIVec3D(1, 64, 64),
        ...     max_level=ScaleLevel.L3,
        ...     batch_z_shards=1,
        ... )
        >>> backend = AcquireZarrBackend(cfg, "/path/to/storage")
        >>>
        >>> # S3 storage (requires environment variables for auth)
        >>> os.environ['AWS_ACCESS_KEY_ID'] = 'your-key'
        >>> os.environ['AWS_SECRET_ACCESS_KEY'] = 'your-secret'
        >>> s3_config = S3Config(
        ...     bucket="my-bucket",
        ...     path="experiments",
        ...     auth_type=S3AuthType.ACCESS_KEY,
        ...     endpoint="s3.amazonaws.com",
        ...     region="us-east-1"
        ... )
        >>> backend = AcquireZarrBackend(cfg, s3_config)
    """

    _streams: dict[ScaleLevel, aqz.ZarrStream] = {}
    _batch_count: int = 0
    _executor: ThreadPoolExecutor

    def _initialize(self) -> None:
        """Initialize acquire-zarr streams for each scale level."""
        self._executor = ThreadPoolExecutor(max_workers=8)
        self._batch_count = 0

        # Create a stream for each scale level
        for level in self.cfg.max_level.levels:
            self._initialize_stream(level)

    def _initialize_stream(self, level: ScaleLevel) -> None:
        """
        Create an acquire-zarr stream for a given scale level.

        Args:
            level: The scale level to initialize
        """
        from ome_zarr_writer.s3_utils import S3Config

        # Get scaled dimensions
        scaled_shape = level.scale(self.cfg.volume_shape)
        scaled_shard = level.scale(self.cfg.shard_shape)
        scaled_chunk = level.scale(self.cfg.chunk_shape)

        # Configure dimensions for acquire-zarr
        # Note: acquire-zarr expects dimensions in order they'll be written
        dimensions = [
            aqz.Dimension(
                name="z",
                type=aqz.DimensionType.SPACE,
                array_size_px=scaled_shape.z,
                chunk_size_px=scaled_chunk.z,
                shard_size_chunks=max(1, scaled_shard.z // scaled_chunk.z),
            ),
            aqz.Dimension(
                name="y",
                type=aqz.DimensionType.SPACE,
                array_size_px=scaled_shape.y,
                chunk_size_px=scaled_chunk.y,
                shard_size_chunks=max(1, scaled_shard.y // scaled_chunk.y),
            ),
            aqz.Dimension(
                name="x",
                type=aqz.DimensionType.SPACE,
                array_size_px=scaled_shape.x,
                chunk_size_px=scaled_chunk.x,
                shard_size_chunks=max(1, scaled_shard.x // scaled_chunk.x),
            ),
        ]

        # Create array settings
        array_settings = aqz.ArraySettings(
            output_key=str(level.value),
            data_type=np.uint16,
            dimensions=dimensions,
        )

        # Configure stream settings based on storage type
        if isinstance(self.storage_root, S3Config):
            # S3 storage: use bucket path structure
            # storage_root already has the .ome.zarr suffix from Backend.__init__
            level_config = self.storage_root / str(level.value)

            stream_settings = aqz.StreamSettings(
                store_path=level_config.path,
                overwrite=self.overwrite,
            )
            stream_settings.arrays = [array_settings]
            stream_settings.s3 = s3_settings_from_config(level_config)

            print(
                f"  Initialized acquire-zarr S3 stream for level {level} at s3://{level_config.bucket}/{level_config.path}"
            )
        else:
            # Local filesystem storage
            level_path = level.get_path(str(self.storage_root))
            level_path.parent.mkdir(parents=True, exist_ok=True)

            stream_settings = aqz.StreamSettings(
                store_path=str(level_path),
                overwrite=self.overwrite,
            )
            stream_settings.arrays = [array_settings]

            print(f"  Initialized acquire-zarr stream for level {level}")

        # Create the stream
        stream = aqz.ZarrStream(stream_settings)
        self._streams[level] = stream

    def write_batch(self, buffer: MultiScaleBuffer) -> bool:
        """
        Write all scale levels of a batch to acquire-zarr streams in parallel.

        Args:
            buffer: MultiScaleBuffer with computed pyramid

        Returns:
            True on success, False on failure
        """
        if buffer.batch_idx is None:
            raise ValueError("Buffer must have a batch_idx assigned")

        # Get z-range for this batch
        z_start, z_end = self.cfg.get_batch_z_range(buffer.batch_idx)

        # Submit all scale writes in parallel
        futures = []
        for level in buffer.max_level.levels:
            future = self._executor.submit(
                self._write_single_scale,
                level,
                buffer,
                z_start,
                z_end,
            )
            futures.append(future)

        # Wait for all to complete
        results = [f.result() for f in futures]
        success = all(results)

        if success:
            self._batch_count += 1

        return success

    def _write_single_scale(
        self,
        level: ScaleLevel,
        buffer: MultiScaleBuffer,
        z_start: int,
        z_end: int,
    ) -> bool:
        """
        Write a single scale level to acquire-zarr stream.

        Args:
            level: Scale level to write
            buffer: Buffer containing data
            z_start: Start z-coordinate (L0 coordinates)
            z_end: End z-coordinate (L0 coordinates, exclusive)

        Returns:
            True on success, False on failure
        """
        try:
            stream = self._streams[level]
            data = buffer.get_volume(level)

            # Scale the z-coordinates
            z_start_scaled = z_start // level.factor
            z_end_scaled = z_end // level.factor
            data_z = z_end_scaled - z_start_scaled

            # Extract the batch data
            batch_data = data[:data_z, :, :]

            # Write to acquire-zarr
            # Note: acquire-zarr's append() writes the data to the stream
            stream.append(batch_data)

            return True
        except Exception as e:
            # Log error for debugging
            print(f"Error writing {level.name} for batch {buffer.batch_idx}: {e}")
            return False

    def _finalize(self) -> None:
        """Close all acquire-zarr streams and shutdown executor."""
        # Close all streams
        for level, stream in self._streams.items():
            try:
                stream.close()
                print(f"  Closed stream for level {level}")
            except Exception as e:
                print(f"Error closing stream for {level}: {e}")

        self._streams.clear()
        self._executor.shutdown(wait=True)
