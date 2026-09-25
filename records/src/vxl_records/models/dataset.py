"""Logical datasets produced by acquisitions."""

from enum import StrEnum
from typing import Self

from pydantic import Field

from vxl_records.errors import InvalidTransitionError

from ._base import RecordModel
from .location import DatasetLocation, LocationStatus


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


_TRANSITIONS = {
    DatasetStatus.PENDING: {
        DatasetStatus.WRITING,
        DatasetStatus.PARTIAL,
        DatasetStatus.FAILED,
    },
    DatasetStatus.WRITING: {
        DatasetStatus.COMPLETED,
        DatasetStatus.PARTIAL,
        DatasetStatus.FAILED,
    },
}


class Dataset(RecordModel):
    """One channel dataset nested within an acquisition volume."""

    status: DatasetStatus = DatasetStatus.PENDING
    format: DatasetFormat = DatasetFormat.OME_ZARR
    locations: list[DatasetLocation] = Field(default_factory=list)

    def transition(self, status: DatasetStatus) -> Self:
        """Return this dataset in a valid next lifecycle state."""
        if status == self.status:
            return self
        if status not in _TRANSITIONS.get(self.status, set()):
            raise InvalidTransitionError(f"dataset cannot transition from {self.status} to {status}")
        return self.model_copy(update={"status": status})

    def terminalize(self, status: DatasetStatus, location_status: LocationStatus) -> Self:
        """Return a terminal dataset with every location updated atomically."""
        locations = [location.model_copy(update={"status": location_status}) for location in self.locations]
        return self.model_copy(update={"locations": locations}).transition(status)
