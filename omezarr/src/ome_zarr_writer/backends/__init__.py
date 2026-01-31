"""
Storage backends for OME-Zarr streaming.

Import backends directly to avoid importing unnecessary dependencies:

    >>> from ome_zarr_writer.backends.ts import TensorStoreBackend      # Production (requires tensorstore)
    >>> from ome_zarr_writer.backends.zarrs import ZarrsBackend         # Alternative (requires zarr, zarrs)
    >>> from ome_zarr_writer.backends.aqz import AcquireZarrBackend     # Acquire-zarr (requires acquire-zarr)
    >>> from ome_zarr_writer.backends.log import LogBackend             # Testing (no dependencies)

For custom backends:
    >>> from ome_zarr_writer.backends.base import Backend, MultiBackend
"""

from .base import Backend, MultiBackend

# NOTE: Do NOT import concrete backends here to avoid import errors
# if optional dependencies are not installed.
# Users should import them directly:
#   from ome_zarr_writer.backends.ts import TensorStoreBackend
#   from ome_zarr_writer.backends.zarrs import ZarrsBackend
#   from ome_zarr_writer.backends.aqz import AcquireZarrBackend
#   from ome_zarr_writer.backends.log import LogBackend

__all__ = [
    "Backend",
    "MultiBackend",
]
