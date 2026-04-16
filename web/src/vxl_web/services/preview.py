"""Preview service — preview lifecycle + frame distribution + ``preview/*`` WS topics.

No REST routes; all operations are WS-driven except initial status broadcast.
"""

import asyncio
import json
import logging
from typing import Any

from vxl import Session
from vxl.camera.preview import PreviewLevels, PreviewViewport

from .ws import BroadcastCallback

log = logging.getLogger(__name__)


class PreviewService:
    """Wraps ``session.preview`` for WS. Owns frame distribution via ``set_frame_callback``."""

    topic_prefixes: tuple[str, ...] = ("preview/",)

    def __init__(self, session: Session, broadcast: BroadcastCallback) -> None:
        self.session = session
        self.broadcast = broadcast
        self._preview_lock = asyncio.Lock()
        session.preview.set_frame_callback(self._distribute_frames)

    # ---- WS ----

    async def handle_message(self, sender_id: str, topic: str, payload: dict[str, Any]) -> None:
        match topic:
            case "preview/start":
                async with self._preview_lock:
                    await self.session.start_preview()
                self.broadcast({}, with_status=True)
            case "preview/stop":
                async with self._preview_lock:
                    await self.session.stop_preview()
                self.broadcast({}, with_status=True)
            case "preview/viewport":
                await self._handle_viewport(payload, sender_id=sender_id)
            case "preview/levels":
                await self._handle_levels(payload, sender_id=sender_id)
            case "preview/colormap":
                await self._handle_colormap(payload, sender_id=sender_id)

    # ---- Lifecycle ----

    async def close(self) -> None:
        """Detach the frame callback. No device RPCs — rig close handles teardown."""
        self.session.preview.set_frame_callback(None)

    # ---- Private ----

    async def _handle_viewport(self, payload: dict[str, Any], *, sender_id: str | None) -> None:
        viewport = PreviewViewport(
            x=payload.get("x", 0.0),
            y=payload.get("y", 0.0),
            w=payload.get("w", 1.0),
            h=payload.get("h", 1.0),
        )
        await self.session.preview.update_viewport(viewport)
        self.broadcast(
            {
                "topic": "preview/viewport",
                "payload": {"x": viewport.x, "y": viewport.y, "w": viewport.w, "h": viewport.h},
            },
            exclude=sender_id,
        )

    async def _handle_levels(self, payload: dict[str, Any], *, sender_id: str | None) -> None:
        channel_id = payload.get("channel")
        if not channel_id:
            raise ValueError("Missing 'channel' in levels payload")
        levels = PreviewLevels(min=payload.get("min", 0), max=payload.get("max", 255))
        await self.session.preview.update_levels({channel_id: levels})
        self.broadcast(
            {"topic": "preview/levels", "payload": {"channel": channel_id, "min": levels.min, "max": levels.max}},
            exclude=sender_id,
        )

    async def _handle_colormap(self, payload: dict[str, Any], *, sender_id: str | None) -> None:
        channel_id = payload.get("channel")
        if not channel_id:
            raise ValueError("Missing 'channel' in colormap payload")
        colormap = payload.get("colormap")
        if not colormap:
            raise ValueError("Missing 'colormap' in colormap payload")
        await self.session.preview.update_colormaps({channel_id: colormap})
        self.broadcast(
            {"topic": "preview/colormap", "payload": {"channel": channel_id, "colormap": colormap}},
            exclude=sender_id,
        )

    async def _distribute_frames(self, topic: str, channel: str, packed_data: bytes) -> None:
        """Frame/tile callback: hybrid wire format (JSON envelope + newline + msgpack data)."""
        wire_topic = "preview/frame" if topic == "preview" else "preview/tile"
        envelope = json.dumps({"topic": wire_topic, "channel": channel}).encode("utf-8")
        self.broadcast(envelope + b"\n" + packed_data)
