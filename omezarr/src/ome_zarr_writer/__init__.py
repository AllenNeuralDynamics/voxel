"""ome-zarr-writer: high-performance streaming acquisition to OME-Zarr.

A streaming writer for OME-Zarr v3 volumes with real-time multiscale pyramid
generation during microscopy acquisition. Frames are ingested one at a time;
the writer batches them, downsamples asynchronously, and flushes each batch.

Basic usage -- write a single-channel volume to a local dataset (the ``.ome.zarr`` suffix
is added by the writer, so pass a bare base path):
    >>> from ome_zarr_writer import Local, OMEZarrWriter, ScaleLevel, UIVec3D, UVec3D, WriterConfig
    >>>
    >>> config = WriterConfig(
    ...     volume_shape=UIVec3D(z=1000, y=2048, x=2048),
    ...     voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
    ...     max_level=ScaleLevel.L5,
    ... )
    >>> writer = OMEZarrWriter(config, Local(target="/path/to/experiment"), slots=6)
    >>> for frame in camera.stream():
    ...     writer.add_frame(frame)
    >>> writer.close()

Write to S3 with a `Storage` variant -- `DirectS3` writes straight to S3, `StagedS3` stages
shards to local scratch then uploads them. The `S3Store` connection carries endpoint/region/
profile (credentials come from the AWS chain):
    >>> from cloudpathlib import S3Path
    >>> from ome_zarr_writer import S3Store, StagedS3
    >>> storage = StagedS3(
    ...     scratch="/fast/scratch",
    ...     target=S3Path("s3://my-bucket/experiment"),
    ...     store=S3Store(endpoint="http://10.0.0.1", region="us-east-1"),
    ... )
    >>> writer = OMEZarrWriter(config, storage, slots=6)

The array backend (`ArrayWriter.Backend.TS` / `.ZARRS`) and ring-buffer mode
(`PyramidRingBuffer.THREADED` / `.PROCESS`) are `OMEZarrWriter` constructor options.
"""

from vxlib.vec import UIVec2D, UIVec3D, UVec3D

from .buffer import BufferSlot, BufferStage, BufferStatus, PyramidRingBuffer
from .dataset import Compression, DownscaleType, Dtype, ScaleLevel
from .storage import DirectS3, Local, S3Store, StagedS3, StagingConfig, Storage
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
    "S3Store",
    "StagingConfig",
    "Storage",
    "Local",
    "DirectS3",
    "StagedS3",
]
