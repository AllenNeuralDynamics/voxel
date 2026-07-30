"""Logical acquisition storage requests and acquisition-root manifest persistence."""

from pathlib import PurePosixPath
from typing import Self

from pydantic import Field, model_validator

from ._base import CatalogModel


class RemoteTarget(CatalogModel):
    """An object-store destination resolved from a node's configured store registry."""

    store: str = Field(min_length=1)
    root: str = Field(min_length=1)
    stage: bool = False


class StorageSpec(CatalogModel):
    """A portable write destination with no machine-local resolution behavior."""

    path: PurePosixPath
    remote: RemoteTarget | None = None

    @model_validator(mode="after")
    def _check_path(self) -> Self:
        if self.path.is_absolute() or ".." in self.path.parts:
            raise ValueError("path must be relative and stay under the storage root")
        if not self.path.parts:
            raise ValueError("path must not be empty")
        return self
