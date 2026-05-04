"""PreviewService — preview lifecycle, viewport/levels/colormap commands, frame distribution.

All preview I/O flows through :class:`vxl_web.wire.MsgBus`:
  - Inbound commands (typed, Pydantic-validated) registered via ``bus.on_command``.
  - Outbound state-change events (``preview.{viewport,levels,colormap}.changed``).
  - Outbound frame stream as raw bytes on per-channel topics
    (``preview.frame.{channel}``, ``preview.tile.{channel}``); the body is the
    msgpack-packed camera payload, decoded on the frontend.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from vxl import Session
from vxl.camera.preview import PreviewViewport
from vxl_web.protocol import Empty
from vxl_web.protocol.preview import PreviewColormapUpdate, PreviewLevelsUpdate
from vxl_web.wire import ClientId, MsgBus

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)


class PreviewService:
    """Wraps ``session.preview`` for the bus."""

    def __init__(self, session: Session, bus: MsgBus) -> None:
        self.session = session
        self.bus = bus
        self._preview_lock = asyncio.Lock()
        self._unsubs: list[Callable[[], None]] = [
            bus.on_command("preview.start", Empty, self._handle_start),
            bus.on_command("preview.stop", Empty, self._handle_stop),
            bus.on_command("preview.pause", Empty, self._handle_pause),
            bus.on_command("preview.resume", Empty, self._handle_resume),
            bus.on_command("preview.viewport.set", PreviewViewport, self._handle_viewport_set),
            bus.on_command("preview.levels.set", PreviewLevelsUpdate, self._handle_levels_set),
            bus.on_command("preview.colormap.set", PreviewColormapUpdate, self._handle_colormap_set),
        ]
        session.preview.set_frame_callback(self._distribute_frames)

    async def close(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self.session.preview.set_frame_callback(None)

    # ---- Bus command handlers ----

    async def _handle_start(self, _cmd: Empty, _sender_id: ClientId) -> None:
        async with self._preview_lock:
            await self.session.start_preview()

    async def _handle_stop(self, _cmd: Empty, _sender_id: ClientId) -> None:
        async with self._preview_lock:
            await self.session.stop_preview()

    async def _handle_pause(self, _cmd: Empty, sender_id: ClientId) -> None:
        if (client := self.bus.get_client(sender_id)) is not None:
            client.pause()

    async def _handle_resume(self, _cmd: Empty, sender_id: ClientId) -> None:
        if (client := self.bus.get_client(sender_id)) is not None:
            client.resume()

    async def _handle_viewport_set(self, viewport: PreviewViewport, sender_id: ClientId) -> None:
        await self.session.preview.update_viewport(viewport)
        self.bus.broadcast("preview.viewport.changed", viewport, exclude=sender_id)

    async def _handle_levels_set(self, cmd: PreviewLevelsUpdate, sender_id: ClientId) -> None:
        await self.session.preview.update_levels({cmd.channel: cmd.levels})
        self.bus.broadcast("preview.levels.changed", cmd, exclude=sender_id)

    async def _handle_colormap_set(self, cmd: PreviewColormapUpdate, sender_id: ClientId) -> None:
        await self.session.preview.update_colormaps({cmd.channel: cmd.colormap})
        self.bus.broadcast("preview.colormap.changed", cmd, exclude=sender_id)

    # ---- Frame distribution ----

    async def _distribute_frames(self, topic: str, channel: str, packed_data: bytes) -> None:
        """Forward camera frames as ``preview.frame.{channel}`` / ``preview.tile.{channel}``.

        ``packed_data`` is already msgpack from ``vxl.camera.preview``; the bus
        wraps it in the ``[topic, body]`` envelope and delivers as raw bytes.
        """
        kind = "frame" if topic == "preview" else "tile"
        self.bus.broadcast(f"preview.{kind}.{channel}", packed_data)
