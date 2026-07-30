"""Durable acquisition catalog contracts and operations for Voxel."""

from .backend import CatalogBackend, FileCatalogBackend
from .catalog import Catalog, StorageRootResolver
from .errors import (
    CatalogError,
    InvalidTransitionError,
    ManifestExistsError,
    ManifestNotFoundError,
    ManifestSyncError,
    RevisionConflictError,
)
from .models import (
    AcquisitionFailure,
    AcquisitionManifest,
    AcquisitionOrigin,
    AcquisitionStatus,
    AcquisitionVolume,
    Dataset,
    DatasetFormat,
    DatasetLocation,
    DatasetStatus,
    LocalLocation,
    LocationRole,
    LocationStatus,
    ObjectLocation,
    RemoteTarget,
    StorageSpec,
    VolumeStatus,
)

__all__ = [
    "AcquisitionFailure",
    "AcquisitionManifest",
    "AcquisitionOrigin",
    "AcquisitionStatus",
    "AcquisitionVolume",
    "Catalog",
    "CatalogBackend",
    "CatalogError",
    "Dataset",
    "DatasetFormat",
    "DatasetLocation",
    "DatasetStatus",
    "FileCatalogBackend",
    "InvalidTransitionError",
    "LocalLocation",
    "LocationRole",
    "LocationStatus",
    "ManifestExistsError",
    "ManifestNotFoundError",
    "ManifestSyncError",
    "ObjectLocation",
    "RemoteTarget",
    "RevisionConflictError",
    "StorageRootResolver",
    "StorageSpec",
    "VolumeStatus",
]
