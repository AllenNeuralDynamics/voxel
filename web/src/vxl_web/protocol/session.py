"""Wire schemas for the ``session.*`` topic namespace.

``SessionStateUpdate`` is also nested inside ``app.status`` (see
:mod:`vxl_web.protocol.app`) — it's the session slice of the global status.
``SessionDetails`` is currently REST-only but is the natural payload for a
future ``session.changed`` event.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from vxl.camera.preview import PreviewConfig
from vxl.session import SessionMode

from .device import DevicesSnapshot

# ==================== Events ====================


class SessionStateUpdate(BaseModel):
    """Session slice of the global status — nested in ``app.status`` payloads."""

    active_profile_id: str | None
    mode: SessionMode
    preview: dict[str, PreviewConfig] = {}
    metadata: dict[str, Any]
    plan: dict[str, Any]
    output: dict[str, Any]
    grid: dict[str, Any]
    stacks: dict[str, Any]
    stack_order: list[str]
    fov: tuple[float, float] | None = None
    timestamp: str


class SessionDetails(BaseModel):
    """One-time session bootstrap — config, metadata schema, device snapshot."""

    config: dict[str, Any]
    metadata_schema: dict[str, Any]
    devices: DevicesSnapshot


# ==================== Requests (REST) ====================


class CreateSessionRequest(BaseModel):
    """POST ``/session`` — create or resume an active session."""

    template: str | None = None
    source_session: str | None = None
    resume: str | None = None
    data_root: str | None = None
    name: str = ""
    description: str = ""
    collection: str = ""
    clear_stacks: bool = False


class MetadataUpdateRequest(BaseModel):
    """PATCH ``/session/metadata``."""

    metadata: dict[str, Any]


class MetadataSchemaRequest(BaseModel):
    """PATCH ``/session/metadata-schema``.

    Wire field ``schema`` maps to Python ``target`` — avoids collision with
    ``BaseModel.schema``.
    """

    model_config = ConfigDict(populate_by_name=True)
    target: str = Field(alias="schema", serialization_alias="schema")


class GridUpdateRequest(BaseModel):
    """PATCH ``/session/grid`` — partial update of grid offsets/overlap."""

    x_offset: float | None = None
    y_offset: float | None = None
    overlap_x: float | None = None
    overlap_y: float | None = None


class OutputUpdateRequest(BaseModel):
    """PATCH ``/session/output`` — partial update of output config."""

    store_path: str | None = None
    max_level: str | None = None
    compression: str | None = None
