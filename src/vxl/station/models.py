"""Transport-neutral models for a control station's materialized feed."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from rigup import DeviceInterface, PropertyModel
from vxl.instrument import AcquisitionMode, ActiveAcquisitionState, InstrumentConfig, InstrumentState
from vxl.instrument.models import TaskTile
from vxl.preview import StreamCursor
from vxl.system import Remote, StationInfo
from vxlib import SchemaModel


class StationStatus(StrEnum):
    """Lifecycle status of the station's active session."""

    IDLE = "idle"
    OPENING = "opening"
    ACTIVE = "active"
    CLOSING = "closing"
    FAULTED = "faulted"
    CLOSED = "closed"


class SessionInfo(SchemaModel):
    """Stable identity of one opened instrument session."""

    id: UUID
    instrument_name: str = Field(min_length=1)


class DeviceState(SchemaModel):
    """Serializable interface and latest-successful properties for one open device."""

    interface: DeviceInterface
    props: dict[str, PropertyModel]


class InstrumentView(InstrumentState):
    """Persisted instrument state enriched with its current runtime projection."""

    config: InstrumentConfig

    mode: AcquisitionMode
    active_profile_id: str = Field(min_length=1)
    preview_revision: int = Field(ge=0)
    fov: tuple[float, float] | None
    routing_targets: dict[str, str]

    task_tiles: list[TaskTile]
    devices: dict[str, DeviceState]
    acquisition: ActiveAcquisitionState | None
    remote_stores: dict[str, Remote]


class SessionView(SchemaModel):
    """Complete bounded view belonging to one opened instrument session."""

    info: SessionInfo
    instrument: InstrumentView


class StationState(SchemaModel):
    """Current reactive lifecycle projection of the live station."""

    status: StationStatus = StationStatus.IDLE
    session: SessionView | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _validate_session_lifecycle(self) -> Self:
        if self.status in {StationStatus.ACTIVE, StationStatus.CLOSING} and self.session is None:
            raise ValueError(f"{self.status} station state requires a session")
        empty_statuses = {StationStatus.IDLE, StationStatus.OPENING, StationStatus.CLOSED}
        if self.status in empty_statuses and self.session is not None:
            raise ValueError(f"{self.status} station state cannot contain a session")
        return self


class StationFeedView(StationState):
    """Complete station state at one position in the ordered feed."""

    cursor: StreamCursor
    observed_at_unix_us: int = Field(ge=0)
    station: StationInfo

    def wire_dict(self) -> dict[str, object]:
        """Serialize the complete view, including fields cleared to null."""
        return self.model_dump(mode="json", exclude_none=False)


__all__ = [
    "DeviceState",
    "InstrumentView",
    "SessionInfo",
    "SessionView",
    "StationFeedView",
    "StationState",
    "StationStatus",
    "StreamCursor",
]
