"""Durable acquisition manifests."""

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from ._base import RecordModel
from .dataset import Dataset
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


class AcquisitionOrigin(RecordModel):
    """The controller and operator that initiated an acquisition."""

    host: str = Field(min_length=1)
    operator: str = Field(min_length=1)


class AcquisitionFailure(RecordModel):
    """A persisted, transport-safe acquisition failure."""

    kind: str = Field(min_length=1)
    message: str = Field(min_length=1)


class AcquisitionVolume(RecordModel):
    """One task/profile capture, with datasets keyed by channel name."""

    task: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    status: VolumeStatus = VolumeStatus.PENDING
    datasets: dict[ChannelName, Dataset] = Field(default_factory=dict)


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
        volume_keys = [(volume.task, volume.profile) for volume in self.volumes]
        if len(volume_keys) != len(set(volume_keys)):
            raise ValueError("task/profile pairs must be unique within an acquisition")

        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at must not precede created_at")
        if self.ended_at is not None and self.ended_at < (self.started_at or self.created_at):
            raise ValueError("ended_at must not precede the acquisition")
        return self
