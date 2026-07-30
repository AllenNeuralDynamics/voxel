"""Logical datasets produced by acquisitions."""

from enum import StrEnum

from pydantic import Field

from ._base import CatalogModel
from .location import DatasetLocation


class DatasetFormat(StrEnum):
    """A dataset's on-disk or object-store representation."""

    OME_ZARR = "ome-zarr"


class DatasetStatus(StrEnum):
    """Acquisition completeness of one logical dataset."""

    PENDING = "pending"
    WRITING = "writing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class Dataset(CatalogModel):
    """One channel dataset nested within an acquisition volume."""

    status: DatasetStatus = DatasetStatus.PENDING
    format: DatasetFormat = DatasetFormat.OME_ZARR
    locations: list[DatasetLocation] = Field(default_factory=list)
