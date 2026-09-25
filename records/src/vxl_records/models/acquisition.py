"""Durable acquisition manifests."""

import datetime
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from vxl_records.errors import InvalidTransitionError, ManifestNotFoundError

from ._base import RecordModel
from .dataset import Dataset, DatasetStatus
from .location import LocationStatus
from .storage import StorageSpec

type ChannelName = Annotated[str, Field(min_length=1)]


class AcquisitionStatus(StrEnum):
    """Lifecycle state of an acquisition."""

    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class VolumeStatus(StrEnum):
    """Lifecycle state of one planned task/profile volume."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


_ACQUISITION_TRANSITIONS = {
    AcquisitionStatus.PREPARING: {
        AcquisitionStatus.RUNNING,
        AcquisitionStatus.FAILED,
        AcquisitionStatus.CANCELLED,
        AcquisitionStatus.INTERRUPTED,
    },
    AcquisitionStatus.RUNNING: {
        AcquisitionStatus.COMPLETED,
        AcquisitionStatus.FAILED,
        AcquisitionStatus.CANCELLED,
        AcquisitionStatus.INTERRUPTED,
    },
}
_VOLUME_TRANSITIONS = {
    VolumeStatus.PENDING: {
        VolumeStatus.RUNNING,
        VolumeStatus.FAILED,
        VolumeStatus.CANCELLED,
        VolumeStatus.SKIPPED,
    },
    VolumeStatus.RUNNING: {
        VolumeStatus.COMPLETED,
        VolumeStatus.FAILED,
        VolumeStatus.CANCELLED,
    },
}


class AcquisitionOrigin(RecordModel):
    """The controller and operator that initiated an acquisition."""

    host: str = Field(min_length=1)
    operator: str = Field(min_length=1)


class AcquisitionFailure(RecordModel):
    """A persisted, transport-safe acquisition failure."""

    kind: str = Field(min_length=1)
    message: str = Field(min_length=1)


class PlannedVolume(RecordModel):
    """One fully resolved volume in acquisition order."""

    task: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    z_start: float = Field(allow_inf_nan=False)
    z_step: float = Field(gt=0, allow_inf_nan=False)
    z_end: float = Field(allow_inf_nan=False)
    routes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_z_range(self) -> Self:
        if self.z_end < self.z_start:
            raise ValueError("volume end must be greater than or equal to start")
        return self

    @property
    def frames_total(self) -> int:
        """Number of frames in this resolved volume."""
        return int((self.z_end - self.z_start) / self.z_step) + 1


class AcquisitionVolume(PlannedVolume):
    """One manifest volume and its acquisition outcome."""

    status: VolumeStatus = VolumeStatus.PENDING
    datasets: dict[ChannelName, Dataset] = Field(default_factory=dict)

    def transition(self, status: VolumeStatus) -> Self:
        """Return this volume in a valid next lifecycle state."""
        if status == self.status:
            return self
        if status not in _VOLUME_TRANSITIONS.get(self.status, set()):
            raise InvalidTransitionError(f"volume cannot transition from {self.status} to {status}")
        return self.model_copy(update={"status": status})

    def register_datasets(self, datasets: Mapping[str, Dataset]) -> Self:
        """Add channel datasets without replacing a conflicting registration."""
        registered = dict(self.datasets)
        for channel, dataset in datasets.items():
            if current := registered.get(channel):
                if current != dataset:
                    raise InvalidTransitionError(f"dataset already registered for channel '{channel}'")
            else:
                registered[channel] = dataset
        return self.model_copy(update={"datasets": registered})

    def complete(self) -> Self:
        """Complete this volume and make all of its datasets available."""
        datasets = {
            channel: dataset.terminalize(DatasetStatus.COMPLETED, LocationStatus.AVAILABLE)
            for channel, dataset in self.datasets.items()
        }
        return self.model_copy(update={"datasets": datasets}).transition(VolumeStatus.COMPLETED)

    def terminalize(
        self,
        status: VolumeStatus,
        *,
        dataset_status: DatasetStatus,
        location_status: LocationStatus,
    ) -> Self:
        """Finish a failed or cancelled volume and its unfinished datasets."""
        if status not in {VolumeStatus.FAILED, VolumeStatus.CANCELLED}:
            raise ValueError("a terminalized volume must be failed or cancelled")
        if dataset_status not in {DatasetStatus.PARTIAL, DatasetStatus.FAILED}:
            raise ValueError("a failed or cancelled volume requires partial or failed datasets")
        if location_status not in {LocationStatus.AVAILABLE, LocationStatus.FAILED}:
            raise ValueError("a failed or cancelled volume requires available or failed locations")
        datasets = {
            channel: dataset.terminalize(dataset_status, location_status)
            if dataset.status in {DatasetStatus.PENDING, DatasetStatus.WRITING}
            else dataset
            for channel, dataset in self.datasets.items()
        }
        volume = self.model_copy(update={"datasets": datasets})
        return volume.transition(status) if volume.status in {VolumeStatus.PENDING, VolumeStatus.RUNNING} else volume


class AcquisitionManifest(RecordModel):
    """The versioned, durable description and outcome of one acquisition."""

    schema_version: Literal["1.0"] = "1.0"
    id: UUID
    revision: int = Field(default=1, ge=1)
    instrument: str = Field(min_length=1)
    origin: AcquisitionOrigin
    status: AcquisitionStatus = AcquisitionStatus.PREPARING
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    failure: AcquisitionFailure | None = None
    storage: StorageSpec
    state_snapshot: dict[str, JsonValue]
    hardware_snapshot: dict[str, JsonValue]
    volumes: list[AcquisitionVolume] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_manifest(self) -> Self:
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at must not precede created_at")
        if self.ended_at is not None and self.ended_at < (self.started_at or self.created_at):
            raise ValueError("ended_at must not precede the acquisition")
        return self

    def transition(
        self,
        status: AcquisitionStatus,
        *,
        at: datetime.datetime,
        failure: AcquisitionFailure | None = None,
    ) -> Self:
        """Return this manifest in a valid next lifecycle state."""
        if status == self.status:
            return self
        if status not in _ACQUISITION_TRANSITIONS.get(self.status, set()):
            raise InvalidTransitionError(f"acquisition cannot transition from {self.status} to {status}")
        if status in {AcquisitionStatus.FAILED, AcquisitionStatus.INTERRUPTED} and failure is None:
            raise InvalidTransitionError(f"{status} requires failure details")
        if status not in {AcquisitionStatus.FAILED, AcquisitionStatus.INTERRUPTED} and failure is not None:
            raise InvalidTransitionError(f"{status} cannot carry failure details")

        changes: dict[str, object] = {"status": status, "failure": failure}
        if status is AcquisitionStatus.RUNNING:
            changes["started_at"] = at
        elif status in {
            AcquisitionStatus.COMPLETED,
            AcquisitionStatus.FAILED,
            AcquisitionStatus.CANCELLED,
            AcquisitionStatus.INTERRUPTED,
        }:
            changes["ended_at"] = at
        return self.model_copy(update=changes)

    def start(self, at: datetime.datetime) -> Self:
        """Start this acquisition."""
        return self.transition(AcquisitionStatus.RUNNING, at=at)

    def complete(self, at: datetime.datetime) -> Self:
        """Complete this acquisition."""
        return self.transition(AcquisitionStatus.COMPLETED, at=at)

    def fail(self, failure: AcquisitionFailure, at: datetime.datetime) -> Self:
        """Fail this acquisition and terminalize every unfinished volume."""
        volumes = [
            volume.transition(VolumeStatus.FAILED)
            if volume.status is VolumeStatus.RUNNING
            else volume.transition(VolumeStatus.SKIPPED)
            if volume.status is VolumeStatus.PENDING
            else volume
            for volume in self.volumes
        ]
        return self.model_copy(update={"volumes": volumes}).transition(
            AcquisitionStatus.FAILED,
            at=at,
            failure=failure,
        )

    def cancel(self, at: datetime.datetime) -> Self:
        """Cancel this acquisition and every unfinished volume."""
        volumes = [
            volume.transition(VolumeStatus.CANCELLED)
            if volume.status in {VolumeStatus.PENDING, VolumeStatus.RUNNING}
            else volume
            for volume in self.volumes
        ]
        return self.model_copy(update={"volumes": volumes}).transition(AcquisitionStatus.CANCELLED, at=at)

    def start_volume(self, volume_index: int) -> Self:
        """Start one volume in the immutable acquisition order."""
        volume = self._get_volume(volume_index).transition(VolumeStatus.RUNNING)
        return self._replace_volume(volume_index, volume)

    def register_datasets(self, volume_index: int, datasets: Mapping[str, Dataset]) -> Self:
        """Register the channel datasets for one volume."""
        volume = self._get_volume(volume_index).register_datasets(datasets)
        return self._replace_volume(volume_index, volume)

    def complete_volume(self, volume_index: int) -> Self:
        """Complete one volume and all of its datasets."""
        return self._replace_volume(volume_index, self._get_volume(volume_index).complete())

    def terminalize_volume(
        self,
        volume_index: int,
        status: VolumeStatus,
        *,
        dataset_status: DatasetStatus,
        location_status: LocationStatus,
    ) -> Self:
        """Fail or cancel one volume and terminalize its unfinished datasets."""
        volume = self._get_volume(volume_index).terminalize(
            status,
            dataset_status=dataset_status,
            location_status=location_status,
        )
        return self._replace_volume(volume_index, volume)

    def _get_volume(self, volume_index: int) -> AcquisitionVolume:
        if not 0 <= volume_index < len(self.volumes):
            raise ManifestNotFoundError(f"volume not found: index={volume_index}")
        return self.volumes[volume_index]

    def _replace_volume(self, volume_index: int, volume: AcquisitionVolume) -> Self:
        volumes = list(self.volumes)
        volumes[volume_index] = volume
        return self.model_copy(update={"volumes": volumes})
