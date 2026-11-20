"""ome-zarr-writer: high-performance streaming acquisition to OME-Zarr.

A streaming writer for OME-Zarr v3 volumes with real-time multiscale pyramid
generation during microscopy acquisition. Frames are ingested one at a time;
the writer batches them, downsamples asynchronously, and flushes each batch.

Basic usage -- write 1 image to a local dataset (the ``.ome.zarr`` suffix is added by the writer, so pass a
bare base path). The image's :class:`~vxlib.vector.Transform` gives its frame count and where each pixel sits:
    >>> from ome_zarr_writer import Local, OMEZarrWriter, WriterSettings
    >>>
    >>> writer = OMEZarrWriter()  # keeps a reusable ring of buffers from image to image
    >>> location = writer.open_image(
    ...     Local(target="/path/to/experiment"), size, dtype, transform, WriterSettings(), ram_bytes
    ... )
    >>> for source in camera.stream():
    ...     with writer.new_frame() as frame:
    ...         frame[...] = source
    >>> writer.close_image()
    >>> writer.release()

Write to S3 with a `Storage` variant -- `DirectS3` writes straight to S3, `StagedS3` stages shards to local
scratch then uploads them. The `S3Store` connection carries endpoint/region/profile (credentials come from the
AWS chain).

The array backend (`ArrayWriter.Backend.TS` / `.ZARRS`) is an `OMEZarrWriter` constructor option; each batch is
downsampled and flushed in a worker process (see `slot.BatchSlot`).
"""

from vxlib.vector import UIVec2D, UIVec3D, UVec3D

from .dataset import Compression, DownscaleType, Dtype, ScaleLevel
from .storage import DirectS3, Local, S3Store, StagedS3, StagingConfig, Storage
from .writer import BatchMetrics, OMEZarrWriter, WriterConfig, WriterSettings

__all__ = [
    "BatchMetrics",
    "Compression",
    "DirectS3",
    "DownscaleType",
    "Dtype",
    "Local",
    "OMEZarrWriter",
    "S3Store",
    "ScaleLevel",
    "StagedS3",
    "StagingConfig",
    "Storage",
    "UIVec2D",
    "UIVec3D",
    "UVec3D",
    "WriterConfig",
    "WriterSettings",
]
