"""Server→client feeds over the WS bus: ``InstrumentFeed`` (one open instrument's reactive surfaces) and
``AppFeed`` (app-level presence + the InstrumentFeed lifecycle)."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel

from rigup import PropResults
from vxl.app import VoxelApp
from vxl.camera import PreviewLevels, PreviewViewport
from vxl.instrument import AcquisitionMode, Instrument, InstrumentState, TaskTile

from .wire import ClientId, MsgBus

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


class InstrumentStatus(BaseModel):
    """Whole-instrument snapshot broadcast on ``instrument.status``."""

    mode: AcquisitionMode
    active_profile_id: str
    fov: tuple[float, float] | None
    state: InstrumentState
    task_tiles: list[TaskTile]


class DevicePropsUpdate(BaseModel):
    """Broadcast on ``device.props.update`` when a device's properties change (a set or a device push)."""

    device: str
    properties: PropResults


class PreviewUpdate(BaseModel):
    """Inbound ``preview.update`` control and outbound ``preview.updates`` echo: any combination of
    viewport / per-channel levels / per-channel colormaps. The echo excludes the originating client, so
    other viewers sync without the sender's drag fighting its own optimistic local state."""

    viewport: PreviewViewport | None = None
    levels: dict[str, PreviewLevels] | None = None
    colormaps: dict[str, str] | None = None


class InstrumentFeed:
    """Bridges the active instrument to the bus: relays its reactive surfaces outbound, and routes the
    inbound ``preview.update`` control. Both directions share the instrument's lifecycle (attach/detach)."""

    def __init__(self, instrument: Instrument, bus: MsgBus) -> None:
        self._inst = instrument
        self._bus = bus
        self._unsubs: list[Teardown] = []

    def attach(self) -> None:
        """Subscribe the outbound streams and broadcast an initial status."""
        i, bus = self._inst, self._bus
        self._unsubs += [
            i.state.subscribe(lambda _s: self.broadcast_status()),
            i.mode.subscribe(lambda _m: self.broadcast_status()),
            i.active_profile_id.subscribe(lambda _id: self.broadcast_status()),
            i.task_tiles.subscribe(lambda _t: self.broadcast_status()),
            i.fov.subscribe(lambda _f: self.broadcast_status()),
            i.progress.subscribe(lambda p: bus.broadcast("acquisition.progress", p)),
            i.frames.subscribe(self._on_frame),
            i.tiles.subscribe(self._on_tiles),
        ]
        self._unsubs += [
            handle.props.subscribe(self._forward_props(device_id)) for device_id, handle in i.hal.devices.items()
        ]
        self._unsubs.append(bus.on_command("preview.update", PreviewUpdate, self._on_preview_update))
        self.broadcast_status()

    def detach(self) -> None:
        """Release all subscriptions. Idempotent."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    async def _on_preview_update(self, cmd: PreviewUpdate, client_id: ClientId) -> None:
        """Apply a viewport/levels/colormap change, then echo it to the other viewers."""
        if cmd.viewport is not None:
            self._inst.update_viewport(cmd.viewport)
        if cmd.levels is not None:
            self._inst.update_levels(cmd.levels)
        if cmd.colormaps is not None:
            self._inst.update_colormaps(cmd.colormaps)
        self._bus.broadcast("preview.updates", cmd, exclude=client_id)

    def broadcast_status(self) -> None:
        i = self._inst
        self._bus.broadcast(
            "instrument.status",
            InstrumentStatus(
                mode=i.mode.value,
                active_profile_id=i.active_profile_id.value,
                fov=i.fov.cache,
                state=i.state.value,
                task_tiles=i.task_tiles.value,
            ),
        )

    async def _on_frame(self, item: tuple[str, bytes]) -> None:
        channel, data = item
        self._bus.broadcast(f"preview.frame.{channel}", data)

    async def _on_tiles(self, item: tuple[str, bytes]) -> None:
        channel, data = item
        self._bus.broadcast(f"preview.tile.{channel}", data)

    def _forward_props(self, device_id: str) -> Callable[[PropResults], None]:
        def forward(props: PropResults) -> None:
            self._bus.broadcast("device.props.update", DevicePropsUpdate(device=device_id, properties=props))

        return forward


class AppStatus(BaseModel):
    """App-level presence, broadcast on ``app.status``: the active instrument's name, or ``None``."""

    active: str | None


class AppFeed:
    """Publishes app-level presence on ``app.status`` and owns the per-instrument ``InstrumentFeed``,
    both driven by ``VoxelApp.active``."""

    def __init__(self, app: VoxelApp, bus: MsgBus) -> None:
        self._app = app
        self._bus = bus
        self._instrument_feed: InstrumentFeed | None = None
        self._unsubs: list[Teardown] = []

    def attach(self) -> None:
        """Track ``app.active``; seed the current presence + feed, then react to every change."""
        self._unsubs.append(self._app.active.subscribe(self._on_active))
        self._on_active(self._app.active.value)

    def detach(self) -> None:
        """Release the app subscription and tear down the active instrument feed, if any. Idempotent."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        if self._instrument_feed is not None:
            self._instrument_feed.detach()
            self._instrument_feed = None

    def broadcast_status(self) -> None:
        active = self._app.active.value
        self._bus.broadcast("app.status", AppStatus(active=active.path.stem if active is not None else None))

    def _on_active(self, instrument: Instrument | None) -> None:
        if self._instrument_feed is not None:
            self._instrument_feed.detach()
            self._instrument_feed = None
        if instrument is not None:
            self._instrument_feed = InstrumentFeed(instrument, self._bus)
            self._instrument_feed.attach()
        self.broadcast_status()
