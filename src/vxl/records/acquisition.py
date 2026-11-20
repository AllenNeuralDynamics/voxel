"""The record of 1 acquisition: what ran, and the facts of what happened to each visit and each image.

The record stores facts only: times, results, failures, frames written and locations. Each status is worked out from
them, so a wrong mix of statuses cannot be stored. ``acquisition.json`` holds the same facts and adds the statuses
for readers.
"""

import datetime
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, model_validator
from vxlib.imaging.writer import FrameRange
from vxlib.issues import Failure
from vxlib.schema import FrozenModel
from vxlib.vector import Transform

from vxl.storage import ImageLocation, StorageSpec

SCHEMA = "voxel.acquisition/1"
"""The name and major version of the public form. A change that breaks a reader gets a new major version."""

type Name = Annotated[str, Field(min_length=1)]

type VisitResult = Literal["completed", "failed", "cancelled", "skipped"]
"""How a visit ended. ``skipped``: the acquisition ended before it started."""

type AcquisitionResult = Literal["completed", "failed", "cancelled", "interrupted"]
"""How an acquisition ended. ``interrupted``: the station stopped while it ran."""


class AcquisitionStatus(StrEnum):
    """Where an acquisition is: its result once it ended."""

    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class VisitStatus(StrEnum):
    """Where a visit is: its result once it ended."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class ImageStatus(StrEnum):
    """How complete an image is. ``partial``: some of its frames were written before its visit ended. ``gaps``: every
    frame was written or dropped, and some were dropped."""

    PENDING = "pending"
    WRITING = "writing"
    COMPLETED = "completed"
    GAPS = "gaps"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class ImageFormat(StrEnum):
    """How an image is stored."""

    OME_ZARR = "ome-zarr"


class Image(FrozenModel):
    """1 camera's image of 1 visit. ``transform`` gives its shape and where each pixel sits, in specimen µm; its first
    axis counts the frames. ``dropped`` holds the frames the writer dropped because every buffer was busy."""

    format: ImageFormat = ImageFormat.OME_ZARR
    transform: Transform
    locations: list[ImageLocation] = Field(default_factory=list)
    frames_written: int = Field(default=0, ge=0)
    dropped: list[FrameRange] = Field(default_factory=list)

    @property
    def frames_total(self) -> int:
        """The frames planned."""
        return self.transform.shape[0]

    @property
    def frames_dropped(self) -> int:
        return sum(frames.count for frames in self.dropped)


class Visit(FrozenModel):
    """1 piece of the plan that runs on its own: 1 profile of 1 task, at 1 place. ``channels`` holds the image of each
    camera of each channel."""

    task: Name
    profile: Name
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    result: VisitResult | None = None
    failures: list[Failure] = Field(default_factory=list)
    channels: dict[Name, dict[Name, Image]] = Field(min_length=1)

    def images(self) -> dict[str, Image]:
        """Each image of the visit, by camera."""
        return {camera: image for cameras in self.channels.values() for camera, image in cameras.items()}

    def with_images(self, images: dict[str, Image]) -> Self:
        """The visit with each image of ``images`` in place of its camera's."""
        channels = {
            name: {camera: images.get(camera, image) for camera, image in cameras.items()}
            for name, cameras in self.channels.items()
        }
        return self.model_copy(update={"channels": channels})

    @property
    def status(self) -> VisitStatus:
        """Its result once it ended; before that, running once it started, and pending until then."""
        if self.result is not None:
            return VisitStatus(self.result)
        return VisitStatus.RUNNING if self.started_at is not None else VisitStatus.PENDING

    @property
    def progress(self) -> tuple[int, int]:
        """The frames done and the frames planned, for the camera that is furthest behind."""
        images = self.images().values()
        return min(image.frames_written for image in images), max(image.frames_total for image in images)

    def image_status(self, camera: str) -> ImageStatus:
        """How complete the image of ``camera`` is, from its frames and the visit's result."""
        image = self.images()[camera]
        if image.frames_written == image.frames_total:
            return ImageStatus.COMPLETED
        if image.frames_written + image.frames_dropped == image.frames_total:
            return ImageStatus.GAPS
        if self.result is None:
            return ImageStatus.WRITING if image.locations else ImageStatus.PENDING
        if self.result == "skipped":
            return ImageStatus.SKIPPED
        return ImageStatus.PARTIAL if image.frames_written else ImageStatus.FAILED

    def missing(self) -> dict[str, int]:
        """Each camera that neither wrote nor dropped all the frames planned, with how many it misses."""
        return {
            camera: missing
            for camera, image in self.images().items()
            if (missing := image.frames_total - image.frames_written - image.frames_dropped) > 0
        }


class Acquisition(FrozenModel):
    """The record of 1 acquisition. ``instrument_config`` and ``instrument_state`` are what ran, frozen at Start, with
    the metadata of each task in the plan. ``revision`` grows by 1 with each change."""

    schema_name: Literal["voxel.acquisition/1"] = Field(default=SCHEMA, alias="schema")
    id: UUID
    revision: int = Field(default=1, ge=1)
    operator: Name
    host: Name
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    result: AcquisitionResult | None = None
    failures: list[Failure] = Field(default_factory=list)
    storage: StorageSpec
    instrument_config: dict[str, JsonValue]
    instrument_state: dict[str, JsonValue]
    visits: list[Visit] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not isinstance(self.instrument_config.get("id"), str):
            raise ValueError("instrument_config must give the instrument's 'id'")
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at must not come before created_at")
        if self.ended_at is not None and self.ended_at < (self.started_at or self.created_at):
            raise ValueError("ended_at must not come before the acquisition")
        return self

    @property
    def instrument(self) -> str:
        """The id of the instrument that ran it."""
        return str(self.instrument_config["id"])

    @property
    def status(self) -> AcquisitionStatus:
        """Its result once it ended; before that, running once it started, and preparing until then."""
        if self.result is not None:
            return AcquisitionStatus(self.result)
        return AcquisitionStatus.RUNNING if self.started_at is not None else AcquisitionStatus.PREPARING

    def changed(self, **changes: object) -> Self:
        """The next revision, with ``changes`` to its fields, checked as a whole."""
        return self.model_validate({**self.model_dump(), **changes, "revision": self.revision + 1})

    def ended(self, result: AcquisitionResult, at: datetime.datetime, failures: Sequence[Failure] = ()) -> Self:
        """The next revision, ended with ``result`` at ``at``. A visit that never started is skipped; a visit still
        open ends cancelled with a cancelled acquisition, and failed otherwise."""
        still_open: VisitResult = "cancelled" if result == "cancelled" else "failed"
        visits = [
            visit.model_copy(update={"result": "skipped"})
            if visit.started_at is None
            else visit.model_copy(update={"result": still_open, "ended_at": at})
            if visit.result is None
            else visit
            for visit in self.visits
        ]
        return self.changed(result=result, ended_at=at, failures=[*self.failures, *failures], visits=visits)

    def for_readers(self) -> dict[str, Any]:
        """The form of ``acquisition.json``: the stored facts, with each status worked out and added."""
        data = self.model_dump(mode="json", by_alias=True)
        data["status"] = self.status.value
        for visit, out in zip(self.visits, data["visits"], strict=True):
            out["status"], out["progress"] = visit.status.value, list(visit.progress)
            for cameras in out["channels"].values():
                for camera, image in cameras.items():
                    image["status"] = visit.image_status(camera).value
        return data
