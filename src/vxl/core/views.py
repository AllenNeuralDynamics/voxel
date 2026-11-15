"""What screens see: each open device, the open instrument, and the station's status."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, model_validator
from rigup.activity import ActivityInfo
from rigup.device import DeviceInterface
from rigup.device.results import PropModel
from vxlib.schema import FrozenModel

from vxl.core.instrument.config import DeviceUid, InstrumentConfig
from vxl.core.instrument.state import InstrumentState
from vxl.preview import StreamCursor
from vxl.system import Remote


class DeviceView(FrozenModel):
    """1 open device as a screen sees it: what it said it is when it opened, and its last properties read."""

    interface: DeviceInterface
    props: dict[str, PropModel]


class StationInfo(BaseModel):
    """Stable public identity of a Voxel control station."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str


class StationStatus(StrEnum):
    """Lifecycle status of the station's active session."""

    IDLE = "idle"
    OPENING = "opening"
    ACTIVE = "active"
    CLOSING = "closing"
    FAULTED = "faulted"
    CLOSED = "closed"


class SessionInfo(FrozenModel):
    """Stable identity of one opened instrument session."""

    id: UUID
    instrument_name: str = Field(min_length=1)


class InstrumentView(FrozenModel):
    """The open instrument as a screen sees it: its ``rig.yaml``, its saved state, what runs, its devices, and the
    object stores that every camera can write to. ``config`` and ``state`` keep every field of the kind of
    instrument."""

    config: SerializeAsAny[InstrumentConfig]
    state: SerializeAsAny[InstrumentState]
    activities: tuple[ActivityInfo, ...]
    device_views: dict[DeviceUid, DeviceView]
    remote_stores: dict[str, Remote]


class SessionView(FrozenModel):
    """Complete bounded view belonging to one opened instrument session."""

    info: SessionInfo
    instrument: InstrumentView


class StationView(FrozenModel):
    """The live station as a screen sees it: its phase, its open session, and its last error."""

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


class StationFeedView(StationView):
    """The station view at 1 place in the ordered feed."""

    cursor: StreamCursor
    observed_at_unix_us: int = Field(ge=0)
    station: StationInfo

    def wire_dict(self) -> dict[str, object]:
        """Serialize the complete view, including fields cleared to null."""
        return self.model_dump(mode="json", exclude_none=False)


__all__ = [
    "DeviceView",
    "InstrumentView",
    "SessionInfo",
    "SessionView",
    "StationFeedView",
    "StationStatus",
    "StationView",
]
