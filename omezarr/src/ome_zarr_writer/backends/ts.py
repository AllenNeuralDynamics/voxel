from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ome_zarr_writer.buffer import MultiScaleBuffer
from ome_zarr_writer.types import ScaleLevel, Compression

from ome_zarr_writer.backends.base import Backend
import numpy as np
import tensorstore as ts
import pydantic_tensorstore as pts

from ome_zarr_writer.s3_utils import S3Config

_BLOSC_LZ4 = [
    pts.Zarr3CodecBlosc(
        configuration=pts.Zarr3CodecBlosc.BloscConfig(
            cname="lz4",  # Fast, good compression
            clevel=3,  # Light compression for speed
            shuffle="bitshuffle",  # Critical for uint16!
            typesize=2,  # uint16 = 2 bytes
        )
    ),
]

_COMPRESSION_CODECS_MAP = {
    Compression.NONE: None,
    Compression.GZIP: [pts.Zarr3CodecGzip(configuration=pts.Zarr3CodecGzip.GzipConfig(level=3))],
    Compression.ZSTD: [pts.Zarr3CodecZstd(configuration=pts.Zarr3CodecZstd.ZstdConfig(level=3))],
    Compression.LZ4: _BLOSC_LZ4,
    Compression.BLOSC_LZ4: _BLOSC_LZ4,
    Compression.BLOSC_ZSTD: [
        pts.Zarr3CodecBlosc(
            configuration=pts.Zarr3CodecBlosc.BloscConfig(
                cname="zstd",  # Fast, good compression
                clevel=3,  # Light compression for speed
                shuffle="bitshuffle",  # Critical for uint16!
                typesize=2,  # uint16 = 2 bytes
            )
        ),
    ],
}


class TensorStoreBackend(Backend):
    """
    TensorStore-based writer for multi-scale Zarr v3 arrays.

    Writes each scale level to a separate Zarr array using TensorStore's
    sharding_indexed codec for efficient chunked storage.

    Features:
    - Parallel writes across scale levels
    - Pre-allocated arrays for consistent metadata
    - Optimized compression for uint16 microscopy data
    """

    _stores: dict[ScaleLevel, Any] = {}
    _write_executor: ThreadPoolExecutor
    _batch_count = 0

    def _initialize(self):
        self._write_executor = ThreadPoolExecutor(max_workers=8)
        self._batch_count = 0
        for level in self.cfg.max_level.levels:
            self._initialize_store(level)

    def _get_kvstore(self, level: ScaleLevel) -> pts.FileKvStore | pts.S3KvStore:
        """Get kvstore configuration for a given level. Override in subclasses for different storage backends."""
        if isinstance(self.storage_root, S3Config):
            level_config = self.storage_root / str(level.value)
            return s3_kvstore(level_config)
        return pts.FileKvStore(path=str(level.get_path(str(self.storage_root))))

    def _initialize_store(self, level):
        """Create a TensorStore array for a given level."""
        store = self.storage_root / str(level.value)
        pts_spec = pts.Zarr3Spec(
            kvstore=make_kvstore(store),
            metadata=pts.Zarr3Metadata(
                data_type=pts.DataType.UINT16,
                shape=[*level.scale(self.cfg.volume_shape)],
                dimension_names=["z", "y", "x"],
                chunk_grid=pts.Zarr3ChunkGrid(
                    configuration=pts.Zarr3ChunkConfiguration(chunk_shape=[*level.scale(self.cfg.shard_shape)])
                ),
                codecs=[
                    pts.Zarr3CodecShardingIndexed(
                        configuration=pts.Zarr3CodecShardingIndexed.ShardingIndexedConfig(
                            chunk_shape=[*level.scale(self.cfg.chunk_shape)],
                            codecs=_COMPRESSION_CODECS_MAP[self.cfg.compression],
                            index_codecs=[pts.Zarr3CodecCRC32C()],
                        )
                    ),
                ],
            ),
        )
        ts_spec = pts_spec.to_tensorstore()
        self._stores[level] = ts.open(ts_spec, create=True, delete_existing=self.overwrite).result()  # pyright: ignore reportAttributeAccessIssue
        print(f"  Initialized store for level {level}")

    def write_batch(self, buffer: MultiScaleBuffer) -> bool:
        """
        Write all scale levels of a batch to TensorStore in parallel.

        Args:
            buffer: MultiScaleBuffer with computed pyramid (called during FLUSHING)

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
            future = self._write_executor.submit(self._write_single_scale, level, buffer, z_start, z_end)
            futures.append(future)

        # Wait for all to complete
        results = [f.result() for f in futures]
        success = all(results)

        if success:
            self._batch_count += 1

        return success

    def _write_single_scale(self, level: ScaleLevel, buffer: MultiScaleBuffer, z_start: int, z_end: int) -> bool:
        """
        Write a single scale level to TensorStore.

        Args:
            level: Scale level to write
            buffer: Buffer containing data
            z_start: Start z-coordinate (L0 coordinates)
            z_end: End z-coordinate (L0 coordinates, exclusive)

        Returns:
            True on success, False on failure
        """
        try:
            store = self._stores[level]
            data = buffer.get_volume(level)

            # Scale the z-coordinates
            z_start_scaled = z_start // level.factor
            z_end_scaled = z_end // level.factor
            data_z = z_end_scaled - z_start_scaled

            # TensorStore write is async, we wait for result
            store[z_start_scaled:z_end_scaled, :, :].write(data[:data_z, :, :]).result()

            return True
        except Exception as e:
            # Log error for debugging
            print(f"Error writing {level.name} for batch {buffer.batch_idx}: {e}")
            return False

    def _finalize(self) -> None:
        """Close all TensorStore handles and shutdown executor."""
        self._write_executor.shutdown(wait=True)
        self._stores.clear()


def s3_kvstore(config: S3Config) -> pts.S3KvStore:
    """Create a TensorStore key-value store for S3."""
    from ome_zarr_writer.s3_utils import S3AuthType

    # Configure authentication
    aws_credentials: dict[str, Any] | None = None
    if config.auth_type == S3AuthType.ANONYMOUS:
        aws_credentials = {"type": "anonymous"}
    elif config.auth_type == S3AuthType.ACCESS_KEY:
        creds = {
            "type": "access_key",
            "access_key": config.access_key_id,
            "secret_key": config.secret_access_key,
        }
        if config.session_token:
            creds["session_token"] = config.session_token
        aws_credentials = creds
    elif config.auth_type == S3AuthType.PROFILE:
        creds = {"type": "profile"}
        if config.profile:
            creds["profile"] = config.profile
        if config.credentials_file:
            creds["filename"] = config.credentials_file
        aws_credentials = creds
    elif config.auth_type == S3AuthType.IAM_ROLE:
        aws_credentials = {"type": "default"}
    # DEFAULT uses TensorStore's default credential chain (None)

    # Configure retry settings if non-default
    s3_request_retries: dict[str, Any] | None = None
    if config.max_retries != 32 or config.initial_retry_delay != 1.0 or config.max_retry_delay != 32.0:
        s3_request_retries = {
            "max_retries": config.max_retries,
            "initial_delay": f"{config.initial_retry_delay}s",
            "max_delay": f"{config.max_retry_delay}s",
        }

    # Configure concurrency context if specified
    context: dict[str, Any] | None = None
    if config.request_concurrency is not None:
        context = {"s3_request_concurrency": {"limit": config.request_concurrency}}

    return pts.S3KvStore(
        bucket=config.bucket,
        path=config.path,
        aws_region=config.region,
        endpoint=config.endpoint,
        host_header=config.host_header,
        requester_pays=config.requester_pays,
        aws_credentials=aws_credentials,
        s3_request_retries=s3_request_retries,
        context=context,
    )


def make_kvstore(src: str | Path | S3Config) -> pts.FileKvStore | pts.S3KvStore:
    if isinstance(src, S3Config):
        return s3_kvstore(src)
    elif isinstance(src, (str, Path)):
        return pts.FileKvStore(path=Path(src).expanduser().resolve().as_posix())
    else:
        raise ValueError(f"Unsupported source type: {type(src)}")


class TSZarrLoader:
    """
    Utility for loading Zarr arrays from local filesystem or S3 using TensorStore.

    Examples:
        >>> # Load from local filesystem
        >>> loader = TSZarrLoader("/path/to/data.zarr", v3=True)
        >>> data = loader.get_3d(z0=0, z1=100)

        >>> # Load from S3 with S3Config
        >>> s3_config = S3Config.from_url("s3://my-bucket/data.zarr", auth_type=S3AuthType.PROFILE, profile="my-profile")
        >>> loader = TSZarrLoader(s3_config, v3=True)
        >>> data = loader.get_3d()

        >>> # Load from S3 anonymously (shorthand)
        >>> s3_config = S3Config.from_url("s3://public-bucket/data.zarr")
        >>> loader = TSZarrLoader(s3_config, v3=True)
        >>> data = loader.get_3d()
    """

    def __init__(self, src: Path | S3Config, v3: bool = False):
        """
        Initialize Zarr loader.

        Args:
            src: Source - can be:
                 - Local path (Path): "/path/to/data.zarr"
                 - S3Config: Created via S3Config.from_url() or S3Config(...)
            v3: Whether to use Zarr v3 format (default: False)
        """
        kvstore_model = make_kvstore(src)
        kvstore_dict = kvstore_model.model_dump(exclude_none=True, mode="json")
        driver = "zarr3" if v3 else "zarr"
        self.store = ts.open({"driver": driver, "kvstore": kvstore_dict}).result()  # type: ignore

    def get_3d(self, z0: int = 1200, n: int | None = 128, z1: int | None = None) -> np.ndarray:
        """
        Load a 3D slice from the Zarr array.

        Args:
            z0: Starting z-index (default: 1200)
            n: Number of z-slices to load (default: 128, ignored if z1 is specified)
            z1: Ending z-index (exclusive, default: z0 + n)

        Returns:
            3D numpy array with shape (z, y, x)
        """
        if z1 is None:
            z1 = z0 + (n or 128)
        slices = (0,) * (self.store.rank - 3) + (slice(z0, z1), slice(None), slice(None))
        return np.array(self.store[slices])


def load_zarr_ts(
    src: str | Path | S3Config,
    v3: bool = False,
    z0: int = 1200,
    n: int | None = 128,
    z1: int | None = None,
) -> np.ndarray:
    """
    Convenience function to load a 3D slice from a Zarr array.

    Args:
        src: Source - can be:
             - Local path (str or Path): "/path/to/data.zarr"
             - S3Config: Created via S3Config.from_url() or S3Config(...)
        v3: Whether to use Zarr v3 format (default: False)
        z0: Starting z-index (default: 1200)
        n: Number of z-slices to load (default: 128, ignored if z1 is specified)
        z1: Ending z-index (exclusive, default: z0 + n)

    Returns:
        3D numpy array with shape (z, y, x)

    Examples:
        >>> # Load from local filesystem
        >>> data = load_zarr_ts("/path/to/data.zarr", v3=True, z0=0, z1=100)

        >>> # Load from S3 anonymously
        >>> s3 = S3Config.from_url("s3://public-bucket/data.zarr")
        >>> data = load_zarr_ts(s3, v3=True)

        >>> # Load from S3 with credentials
        >>> s3 = S3Config.from_url(
        ...     "s3://my-bucket/data.zarr",
        ...     auth_type=S3AuthType.ACCESS_KEY,
        ...     access_key_id="...",
        ...     secret_access_key="..."
        ... )
        >>> data = load_zarr_ts(s3, v3=True)

        >>> # Load from S3 with profile
        >>> s3 = S3Config.from_url("s3://my-bucket/data.zarr", auth_type=S3AuthType.PROFILE, profile="default")
        >>> data = load_zarr_ts(s3, v3=True, z0=1000, z1=1100)
    """
    if isinstance(src, str):
        src = Path(src)
    loader = TSZarrLoader(src, v3)
    return loader.get_3d(z0, n, z1)
