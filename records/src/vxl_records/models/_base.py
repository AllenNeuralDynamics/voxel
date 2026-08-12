"""Shared model configuration for durable Voxel records."""

from pydantic import BaseModel, ConfigDict


class RecordModel(BaseModel):
    """Strict, immutable base for persisted record models."""

    model_config = ConfigDict(extra="forbid", frozen=True)
