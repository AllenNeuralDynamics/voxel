"""Shared model configuration for the catalog contract."""

from pydantic import BaseModel, ConfigDict


class CatalogModel(BaseModel):
    """Strict, immutable base for persisted catalog models."""

    model_config = ConfigDict(extra="forbid", frozen=True)
