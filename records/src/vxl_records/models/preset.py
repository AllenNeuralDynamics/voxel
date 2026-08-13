"""Durable, instrument-scoped reusable configuration records."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue

from ._base import RecordModel


class PresetRecord(RecordModel):
    """One named preset payload scoped to an installed instrument."""

    schema_version: Literal["1.0"] = "1.0"
    id: UUID
    instrument: str = Field(min_length=1)
    name: str = Field(min_length=1)
    created_at: AwareDatetime
    value: dict[str, JsonValue]


__all__ = ["PresetRecord"]
