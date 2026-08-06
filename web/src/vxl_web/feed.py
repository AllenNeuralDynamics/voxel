"""Bridge application and active-instrument updates onto the primary WebSocket bus."""

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from vxl.app import VoxelApp
from vxl.camera import PreviewViewport
from vxl.instrument import Instrument
from vxl.instrument.feed import InstrumentUpdate

from .websocket import ClientId, MsgBus

if TYPE_CHECKING:
    from vxlib import Teardown

log = logging.getLogger(__name__)


class LogMessage(BaseModel):
    """A captured log record. Broadcast live on the ``logs`` topic and served as backlog from ``GET /logs``.

    ``seq`` is a process-monotonic id assigned when the record is delivered; clients merge backlog and live
    records by ``seq`` (dedup + order), so a (re)connecting client never misses or duplicates a log.
    """

    seq: int
    level: str
    message: str
    logger: str
    timestamp: str


class PreviewLevels(BaseModel):
    """Client-owned normalized display bounds for one preview channel."""

    min: float = Field(default=0.0, ge=0.0, le=1.0)
    max: float = Field(default=1.0, ge=0.0, le=1.0)


class PreviewUpdate(BaseModel):
    """Inbound ``preview.update`` control and outbound ``preview.updates`` echo: any combination of
    viewport / per-channel levels. The echo excludes the originating client, so other viewers sync without
    the sender's drag fighting its own optimistic local state."""

    viewport: PreviewViewport | None = None
    levels: dict[str, PreviewLevels] | None = None


class AppStatus(BaseModel):
    """App-level presence, broadcast on ``app.status``: the active instrument's name, or ``None``."""

    active: str | None


class AppFeed:
    """Publish app presence and bridge the active Instrument's owned feed onto the web bus."""

    def __init__(self, app: VoxelApp, bus: MsgBus) -> None:
        self._app = app
        self._bus = bus
        self._instrument_unsub: Teardown | None = None
        self._unsubs: list[Teardown] = []

    def attach(self) -> None:
        """Track the active instrument and register instrument-scoped web controls."""
        self._unsubs = [
            self._app.active.subscribe(self._on_active),
            self._bus.on_command("preview.update", PreviewUpdate, self._on_preview_update),
        ]
        self._on_active(self._app.active.value)

    def detach(self) -> None:
        """Release application, instrument, and command subscriptions. Idempotent."""
        if self._instrument_unsub is not None:
            self._instrument_unsub()
            self._instrument_unsub = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    def _broadcast_status(self) -> None:
        active = self._app.active.value
        self._bus.broadcast("app.status", AppStatus(active=active.path.stem if active is not None else None))

    def _on_active(self, instrument: Instrument | None) -> None:
        if self._instrument_unsub is not None:
            self._instrument_unsub()
            self._instrument_unsub = None
        if instrument is not None:
            self._instrument_unsub = instrument.feed.updates.subscribe(self._forward_instrument_update)
        self._broadcast_status()

    def _forward_instrument_update(self, update: InstrumentUpdate) -> None:
        self._bus.broadcast("instrument.update", update, exclude_unset=True)

    async def _on_preview_update(self, cmd: PreviewUpdate, client_id: ClientId) -> None:
        """Apply viewport control to the active instrument and echo shared preview state."""
        instrument = self._app.active.value
        if instrument is None:
            return
        if cmd.viewport is not None:
            instrument.update_viewport(cmd.viewport)
        self._bus.broadcast("preview.updates", cmd, exclude=client_id)
