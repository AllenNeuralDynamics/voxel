from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator
from vxl_records import AcquisitionManifest, StorageSpec

from .traversal import Tile


class AcquisitionMode(StrEnum):
    IDLE = "idle"
    PREVIEW = "preview"
    CAPTURE = "capture"


class AcquisitionRequest(BaseModel):
    """Parameters of an acquisition run. Shared by the instrument API and web request body."""

    storage: StorageSpec
    task_ids: list[str] | None = None
    operator: str | None = None


class VolumeProgress(BaseModel, frozen=True):
    """Transient frame progress for one task/profile volume.

    A profile's channels capture in synchronized batches, so the captured-frame count is shared across
    them. This state is retained by the instrument for live clients but is not written to durable records.
    """

    task: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    frames_captured: int = Field(ge=0)
    frames_total: int = Field(gt=0)

    @model_validator(mode="after")
    def _check_frames(self) -> Self:
        if self.frames_captured > self.frames_total:
            raise ValueError("frames_captured cannot exceed frames_total")
        return self

    def updated(self, *, frames_captured: int) -> Self:
        return type(self).model_validate({**self.model_dump(), "frames_captured": frames_captured})


class ActiveAcquisitionState(BaseModel, frozen=True):
    """The latest durable manifest plus transient progress for the instrument's current run."""

    manifest: AcquisitionManifest
    progress: VolumeProgress

    @model_validator(mode="after")
    def _check_progress_volume(self) -> Self:
        key = (self.progress.task, self.progress.profile)
        if key not in {(volume.task, volume.profile) for volume in self.manifest.volumes}:
            raise ValueError("progress must identify a volume in the manifest")
        return self


class TaskTile(Tile):
    """A task's footprint tile (a :class:`Tile`) tagged with its ``task_id``. Because :class:`TileOrder`
    is generic over the tile subtype, an ordered ``list[TaskTile]`` carries both the per-task geometry
    and the traversal order — replacing a separate tiles-map and order-list with one value."""

    task_id: str
    routes: dict[str, str]
