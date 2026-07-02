"""ome-zarr-writer: high-performance streaming acquisition to OME-Zarr.

A streaming writer for OME-Zarr v3 volumes with real-time multiscale pyramid
generation during microscopy acquisition. Frames are ingested one at a time;
the writer batches them, downsamples asynchronously, and flushes each batch.

Basic usage -- write a single-channel volume to a local dataset:
    >>> from ome_zarr_writer import OMEZarrWriter, WriterConfig, ScaleLevel
    >>> from ome_zarr_writer import UIVec3D, UVec3D
    >>>
    >>> config = WriterConfig(
    ...     volume_shape=UIVec3D(z=1000, y=2048, x=2048),
    ...     voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
    ...     max_level=ScaleLevel.L5,
    ...     target="/path/to/experiment.ome.zarr",
    ... )
    >>> writer = OMEZarrWriter(config, slots=6)
    >>> for frame in camera.stream():
    ...     writer.add_frame(frame)
    >>> writer.close()

Write to S3 by passing an ``s3://`` target (credentials from the AWS environment
chain), optionally staging through local scratch before upload:
    >>> from cloudpathlib import S3Path
    >>> config = WriterConfig(
    ...     volume_shape=UIVec3D(z=1000, y=2048, x=2048),
    ...     voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
    ...     target=S3Path("s3://my-bucket/experiment.ome.zarr"),
    ...     scratch="/fast/scratch",
    ... )

The array backend (`ArrayWriter.Backend.TS` / `.ZARRS`) and ring-buffer mode
(`PyramidRingBuffer.THREADED` / `.PROCESS`) are `OMEZarrWriter` constructor options.
"""

from vxlib.vec import UIVec2D, UIVec3D, UVec3D

from .buffer import BufferSlot, BufferStage, BufferStatus, PyramidRingBuffer
from .dataset import Compression, DownscaleType, Dtype, ScaleLevel
from .writer import BatchMetrics, OMEZarrWriter, WriterConfig, WriterSettings

__all__ = [
    "OMEZarrWriter",
    "WriterConfig",
    "WriterSettings",
    "DownscaleType",
    "Dtype",
    "ScaleLevel",
    "UIVec2D",
    "UIVec3D",
    "UVec3D",
    "Compression",
    "BatchMetrics",
    "BufferStage",
    "BufferStatus",
    "BufferSlot",
    "PyramidRingBuffer",
]
