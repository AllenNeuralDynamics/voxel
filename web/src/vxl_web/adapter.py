"""Adapt Voxel application state and controls to the web transports."""

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket
from pydantic import BaseModel, Field
from vxl_records import LogEntry

from vxl.app import VoxelApp
from vxl.instrument import Instrument
from vxl.instrument.feed import InstrumentUpdate
from vxl.preview import PreviewViewport

from .websocket import ClientId, MsgBus, PreviewBus

if TYPE_CHECKING:
    from vxlib import Teardown

log = logging.getLogger(__name__)


class PreviewLevels(BaseModel):
    """Client-owned normalized display bounds for one preview channel."""

    min: float = Field(default=0.0, ge=0.0, le=1.0)
    max: float = Field(default=1.0, ge=0.0, le=1.0)


class PreviewUpdate(BaseModel):
    """Bidirectional ``instrument.preview`` state: any combination of
    viewport / per-channel levels. The echo excludes the originating client, so other viewers sync without
    the sender's drag fighting its own optimistic local state."""

    viewport: PreviewViewport | None = None
    levels: dict[str, PreviewLevels] | None = None


class AppStatus(BaseModel):
    """App-level presence, broadcast on ``app.status``: the active instrument's name, or ``None``."""

    active: str | None


class VoxelWebAdapter:
    """Own the web application's realtime message and preview transports.

    The adapter follows :attr:`VoxelApp.active` once, forwards the active
    instrument's ordered updates, and supplies both WebSocket endpoints.
    """

    def __init__(self, app: VoxelApp) -> None:
        self._app = app
        self._messages = MsgBus()
        self._preview = PreviewBus()
        self._instrument_unsub: Teardown | None = None
        self._unsubs: list[Teardown] = []

    def attach(self) -> None:
        """Track the active instrument and register web controls. Idempotent."""
        if self._unsubs:
            return
        self._unsubs = [
            self._app.active.subscribe(self._on_active),
            self._app.records.logs.subscribe(self._publish_log),
            self._messages.on_command("instrument.preview", PreviewUpdate, self._on_preview_update),
        ]
        self._on_active(self._app.active.value)

    async def close(self) -> None:
        """Release subscriptions and close both WebSocket transports. Idempotent."""
        if self._instrument_unsub is not None:
            self._instrument_unsub()
            self._instrument_unsub = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        await self._preview.close()
        await self._messages.close()

    async def serve(self, websocket: WebSocket) -> None:
        """Serve one primary typed-message WebSocket peer."""
        await self._messages.serve(websocket)

    async def serve_preview(self, websocket: WebSocket) -> None:
        """Serve one latest-only preview WebSocket peer."""
        await self._preview.serve(websocket)

    def _publish_log(self, entry: LogEntry) -> None:
        """Publish one committed journal entry on the primary transport."""
        self._broadcast("app.logs", entry)

    def _broadcast(
        self,
        topic: str,
        body: BaseModel,
        *,
        exclude: ClientId | None = None,
        exclude_unset: bool = False,
    ) -> None:
        """Broadcast an internal typed event on the primary message transport."""
        self._messages.broadcast(topic, body, exclude=exclude, exclude_unset=exclude_unset)

    def _broadcast_status(self) -> None:
        active = self._app.active.value
        self._broadcast("app.status", AppStatus(active=active.path.stem if active is not None else None))

    def _on_active(self, instrument: Instrument | None) -> None:
        if self._instrument_unsub is not None:
            self._instrument_unsub()
            self._instrument_unsub = None
        self._preview.set_instrument(instrument)
        if instrument is not None:
            self._instrument_unsub = instrument.feed.updates.subscribe(self._forward_instrument_update)
        self._broadcast_status()

    def _forward_instrument_update(self, update: InstrumentUpdate) -> None:
        self._broadcast("instrument.feed.updates", update, exclude_unset=True)

    async def _on_preview_update(self, cmd: PreviewUpdate, client_id: ClientId) -> None:
        """Apply viewport control to the active instrument and echo shared preview state."""
        instrument = self._app.active.value
        if instrument is None:
            return
        if cmd.viewport is not None:
            instrument.update_viewport(cmd.viewport)
        self._broadcast("instrument.preview", cmd, exclude=client_id)
