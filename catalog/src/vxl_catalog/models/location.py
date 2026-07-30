"""Physical locations of catalogued datasets."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from ._base import CatalogModel


class LocationRole(StrEnum):
    """A location's purpose in the storage lifecycle."""

    STAGING = "staging"
    DESTINATION = "destination"
    REPLICA = "replica"


class LocationStatus(StrEnum):
    """Availability of a dataset at one physical location."""

    PENDING = "pending"
    WRITING = "writing"
    AVAILABLE = "available"
    FAILED = "failed"
    EVICTED = "evicted"


class LocalLocation(CatalogModel):
    """A dataset path on a specific host."""

    kind: Literal["local"] = "local"
    role: LocationRole
    status: LocationStatus
    host: str = Field(min_length=1)
    path: str = Field(min_length=1)


class ObjectLocation(CatalogModel):
    """An object-store key addressable through a host's configured store."""

    kind: Literal["object"] = "object"
    role: LocationRole
    status: LocationStatus
    host: str = Field(min_length=1)
    store: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    key: str = Field(min_length=1)


type DatasetLocation = Annotated[LocalLocation | ObjectLocation, Field(discriminator="kind")]
