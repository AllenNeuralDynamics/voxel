"""Where acquisitions write: the storage that a person asks for, the places where each image lands, and a check
that a computer can write there."""

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from vxlib.schema import FrozenModel


class RemoteTarget(FrozenModel):
    """An object store and the root in it, named in the station's store registry. With ``stage``, a computer writes
    on its own disk first and copies to the store after."""

    store: str = Field(min_length=1)
    root: str = Field(min_length=1)
    stage: bool = False


class StorageSpec(FrozenModel):
    """Where an acquisition writes: ``path`` under each computer's storage root, or under ``remote``. It holds no
    machine's paths, so every computer resolves it to its own."""

    path: PurePosixPath
    remote: RemoteTarget | None = None

    @model_validator(mode="after")
    def _check_path(self) -> Self:
        if self.path.is_absolute() or ".." in self.path.parts:
            raise ValueError("path must be relative and stay under the storage root")
        if not self.path.parts:
            raise ValueError("path must not be empty")
        return self


class StorageStatus(FrozenModel):
    """A computer's check that it can write a storage root. ``free_bytes`` is -1 when the space is unknown, as on
    an object store."""

    host: str
    root: str
    free_bytes: int


class LocationRole(StrEnum):
    """What a location is for: written first and copied later, the final place, or a copy."""

    STAGING = "staging"
    DESTINATION = "destination"
    REPLICA = "replica"


class LocationStatus(StrEnum):
    """Whether an image is complete at a location: still being written, closed with every frame it collected
    written, or not known to be complete because its writer never closed it."""

    WRITING = "writing"
    AVAILABLE = "available"
    FAILED = "failed"


class LocalLocation(FrozenModel):
    """An image as a path on 1 computer."""

    kind: Literal["local"] = "local"
    role: LocationRole
    host: str = Field(min_length=1)
    path: str = Field(min_length=1)


class ObjectLocation(FrozenModel):
    """An image as a key in an object store, which a computer reaches through its configured store."""

    kind: Literal["object"] = "object"
    role: LocationRole
    host: str = Field(min_length=1)
    store: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    key: str = Field(min_length=1)


type ImageLocation = Annotated[LocalLocation | ObjectLocation, Field(discriminator="kind")]
"""1 place where an image is."""
