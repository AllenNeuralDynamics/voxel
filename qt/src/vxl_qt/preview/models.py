"""Preview state store.

:class:`PreviewStore` holds the per-channel overview + tile data decoded from the instrument's preview
streams, plus the shared viewport; :class:`vxl_qt.preview.panel.PreviewPanel` composites and renders it.
"""

import asyncio
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from vxl.camera.preview import (
    PreviewFrame,
    PreviewFrameInfo,
    PreviewLevels,
    PreviewTile,
    PreviewTileInfo,
    PreviewTiles,
    PreviewViewport,
)
from vxl.instrument import Instrument
from vxlib import Teardown


def _decode_image(data: bytes) -> QImage | None:
    """Decode compressed bytes (JPEG/PNG) to a QImage. Safe to run off the UI thread."""
    image = QImage()
    return image if image.loadFromData(data) else None


def _decode_tiles(tiles: list[PreviewTile]) -> list[tuple[int, int, QImage]]:
    """Decode a tile batch to ``(col, row, QImage)`` triples, skipping any that fail to decode."""
    decoded: list[tuple[int, int, QImage]] = []
    for tile in tiles:
        image = QImage()
        if image.loadFromData(tile.data):
            decoded.append((tile.col, tile.row, image))
    return decoded


@dataclass
class ChannelData:
    """Display data for one channel: the overview backdrop, its high-res tile overlay, and the sensor
    geometry needed to lay it out (full sensor size + rotation). Decoded to ``QImage`` for direct
    ``QPainter`` compositing. Histogram accompanies the overview."""

    frame: QImage | None = None  # overview backdrop (full sensor, downsampled)
    colormap: str | None = None
    histogram: list[int] | None = None
    sensor_w: int = 0
    sensor_h: int = 0
    rotation_deg: int = 0
    tiles: dict[str, QImage] = field(default_factory=dict)  # keyed "col:row" at the current tile_scale
    tile_scale: int = -1

    def levels(self, percentile: float = 1.0) -> PreviewLevels:
        """Calculate auto-levels from histogram."""
        if self.histogram is None:
            return PreviewLevels()
        return PreviewLevels.from_histogram(self.histogram, percentile)


class PreviewStore(QObject):
    """Manages preview state: frames, viewport, and interaction."""

    frame_received = Signal(str)  # channel_id
    viewport_changed = Signal(float, float, float, float)  # x, y, w, h
    composite_updated = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._channels: dict[str, ChannelData] = {}
        self._viewport = PreviewViewport()
        self._is_interacting = False
        self._instrument: Instrument | None = None

    @property
    def viewport(self) -> PreviewViewport:
        """Current target viewport state."""
        return self._viewport

    @property
    def is_interacting(self) -> bool:
        """Whether user is currently panning/zooming."""
        return self._is_interacting

    @property
    def channels(self) -> dict[str, ChannelData]:
        """All channel data."""
        return self._channels

    def _channel(self, channel: str) -> ChannelData:
        data = self._channels.get(channel)
        if data is None:
            data = ChannelData()
            self._channels[channel] = data
        return data

    def set_frame(self, channel: str, frame: QImage, info: PreviewFrameInfo, rotation_deg: int) -> None:
        """Store the overview backdrop for a channel, preserving any tile overlay."""
        data = self._channel(channel)
        data.frame = frame
        data.colormap = info.colormap
        data.histogram = info.histogram
        data.sensor_w = info.full_width
        data.sensor_h = info.full_height
        data.rotation_deg = rotation_deg
        self.frame_received.emit(channel)
        self.composite_updated.emit()

    def set_tiles(self, channel: str, info: PreviewTileInfo, tiles: list[tuple[int, int, QImage]]) -> None:
        """Add a batch of high-res tiles for a channel; clear the cache when the pyramid scale changes."""
        data = self._channel(channel)
        if data.tile_scale != info.scale:
            data.tiles.clear()
            data.tile_scale = info.scale
        for col, row, image in tiles:
            data.tiles[f"{col}:{row}"] = image
        self.composite_updated.emit()

    def start_feed(self, instrument: Instrument) -> Teardown:
        """Consume the instrument's live preview streams (overview frames + tiles, preview and
        acquisition alike). Clears stale data on profile switch so a previous profile's channels don't
        linger. Returns a teardown callable that detaches the subscriptions.
        """
        self._instrument = instrument
        unsubs = [
            instrument.frames.subscribe(self._on_frame),
            instrument.tiles.subscribe(self._on_tiles),
            instrument.active_profile_id.subscribe(lambda _id: self.clear_frames()),
        ]

        def teardown() -> None:
            for unsub in unsubs:
                unsub()
            self._instrument = None

        return teardown

    async def _on_frame(self, update: tuple[str, bytes]) -> None:
        # Decode off the UI thread — a synchronous loadFromData would block the qasync (UI) loop.
        channel, data = update
        frame = PreviewFrame.from_packed(data)
        image = await asyncio.get_running_loop().run_in_executor(None, _decode_image, frame.data)
        if image is not None:
            self.set_frame(channel, image, frame.info, self._rotation_for(channel))

    async def _on_tiles(self, update: tuple[str, bytes]) -> None:
        # Decode the whole batch off the UI thread — zoomed in a batch is dozens of tiles, and a
        # synchronous decode of all of them would wedge the UI loop (the beach ball).
        channel, data = update
        batch = PreviewTiles.from_packed(data)
        decoded = await asyncio.get_running_loop().run_in_executor(None, _decode_tiles, batch.tiles)
        if decoded:
            self.set_tiles(channel, batch.info, decoded)

    def _rotation_for(self, channel: str) -> int:
        """The channel's camera rotation (deg) from its channel config + HAL config; 0 if unknown."""
        if self._instrument is None:
            return 0
        channel_config = self._instrument.state.value.imaging.channels.get(channel)
        if channel_config is None:
            return 0
        detection = self._instrument.hal.config.detection.get(channel_config.detection)
        return detection.rotation_deg if detection else 0

    def set_viewport(self, viewport: PreviewViewport) -> None:
        """Update the target viewport state."""
        self._viewport = viewport
        self.viewport_changed.emit(viewport.x, viewport.y, viewport.w, viewport.h)
        self.composite_updated.emit()

    def set_interacting(self, value: bool) -> None:
        """Set interaction state.

        When interaction ends, triggers redraw to remove blur.
        """
        was_interacting = self._is_interacting
        self._is_interacting = value

        if was_interacting and not value:
            self.composite_updated.emit()

    def clear_frames(self) -> None:
        """Clear channel frame data, preserving viewport."""
        self._channels.clear()
        self._is_interacting = False
        self.composite_updated.emit()

    def reset(self) -> None:
        """Clear all state including viewport."""
        self._channels.clear()
        self._viewport = PreviewViewport()
        self._is_interacting = False
        self.composite_updated.emit()

    def get_histogram(self, channel: str) -> list[int] | None:
        """Get the histogram for a channel."""
        if channel in self._channels:
            return self._channels[channel].histogram
        return None

    def get_levels(self, channel: str, percentile: float = 1.0) -> PreviewLevels:
        """Calculate auto-levels for a channel."""
        if channel in self._channels:
            return self._channels[channel].levels(percentile)
        return PreviewLevels()
