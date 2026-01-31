"""
ome-zarr-writer: High-performance streaming acquisition to OME-Zarr.

This package provides a streaming writer for OME-Zarr volumes with real-time
multi-scale pyramid generation during microscopy acquisition.

Basic usage:
    >>> from ome_zarr_writer import OMEZarrWriter, StreamConfig, ScaleLevel
    >>> from ome_zarr_writer.backends.ts import TensorStoreBackend
    >>>
    >>> config = WriterConfig(
    ...     name="experiment_001",
    ...     volume_shape=(1000, 2048, 2048),
    ...     max_level=ScaleLevel.L5
    ... )
    >>>
    >>> backend = TensorStoreBackend(config, storage_root="/path/to/data")
    >>> with OMEZarrWriter(backend) as writer:
    ...     for frame in camera.stream():
    ...         writer.add_frame(frame)

Backend imports (import only what you need):
    >>> from ome_zarr_writer.backends.ts import TensorStoreBackend      # requires: tensorstore
    >>> from ome_zarr_writer.backends.zarrs import ZarrsBackend         # requires: zarr, zarrs
    >>> from ome_zarr_writer.backends.log import LogBackend             # no extra dependencies
"""

from .backends.base import Backend, MultiBackend

# Buffer types (for advanced usage)
from .buffer import (
    BufferStage,
    BufferStatus,
    MultiScaleBuffer,
)

# Configuration
from .config import WriterConfig
from .s3_utils import S3AuthType, S3Config

# Core types
from .types import (
    Compression,
    Dtype,
    ScaleLevel,
)
from vxlib.vec import UIVec2D, UIVec3D, UVec3D
from .writer import OMEZarrWriter, StreamMetrics, StreamStatus

__version__ = "0.1.0"

__all__ = [
    # Main interface
    "OMEZarrWriter",
    "WriterConfig",
    "StreamStatus",
    "StreamMetrics",
    # S3 Configuration
    "S3Config",
    "S3AuthType",
    # Core types
    "Dtype",
    "ScaleLevel",
    "UIVec2D",
    "UIVec3D",
    "UVec3D",
    "Compression",
    # Buffer (advanced)
    "BufferStage",
    "BufferStatus",
    "MultiScaleBuffer",
    # Backend base (for custom backends)
    "Backend",
    "MultiBackend",
    # Version
    "__version__",
]
