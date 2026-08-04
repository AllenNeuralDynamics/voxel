"""Preview state store.

:class:`PreviewStore` holds the per-channel overview + viewport-image data decoded from the instrument's
preview streams, plus the shared viewport; :class:`vxl_qt.preview.panel.PreviewPanel` composites and renders it.
"""

import asyncio
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from vxl.camera.preview import PreviewFrame, PreviewSourceHeader, PreviewViewport
from vxl.instrument import Instrument
from vxlib import Teardown


def _decode_image(data: bytes) -> tuple[PreviewSourceHeader, QImage]:
    """Decode a raw source packet to a display-scaled grayscale image."""
    source = PreviewFrame.from_packed(data)
    pixels = source.decode()
    if source.header.valid_bits < 16:
        maximum = (1 << source.header.valid_bits) - 1
        pixels = (pixels.astype(np.uint32) * 65535 // maximum).astype(np.uint16)
    image = QImage(
        pixels.data,
        source.header.width,
        source.header.height,
        pixels.strides[0],
        QImage.Format.Format_Grayscale16,
    ).copy()
    return source.header, image


@dataclass
class ChannelData:
    """Display data for one channel: the overview backdrop, the coherent high-res viewport image (when
    zoomed) + the sensor-normalized region it covers, and the sensor geometry needed to lay it out (full
    sensor size + rotation). Decoded to ``QImage`` for direct ``QPainter`` compositing."""

    frame: QImage | None = None  # overview backdrop (full sensor, downsampled)
    sensor_w: int = 0
    sensor_h: int = 0
    rotation_deg: int = 0
    source_stream_id: str = ""
    viewport_frame: QImage | None = None  # latest coherent viewport image; None at full viewport
    viewport_rect: PreviewViewport | None = None  # sensor-normalized region covered, including overscan
    viewport_frame_idx: int = -1  # for latest-wins


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

    def set_frame(self, channel: str, frame: QImage, header: PreviewSourceHeader, rotation_deg: int) -> None:
        """Store the overview backdrop for a channel, preserving any tile overlay."""
        data = self._channel(channel)
        if data.source_stream_id != header.source_stream_id:
            data.viewport_frame = None
            data.viewport_rect = None
            data.viewport_frame_idx = -1
            data.source_stream_id = header.source_stream_id
        data.frame = frame
        data.sensor_w = header.sensor_width
        data.sensor_h = header.sensor_height
        data.rotation_deg = rotation_deg
        self.frame_received.emit(channel)
        self.composite_updated.emit()

    def set_viewport_frame(self, channel: str, header: PreviewSourceHeader, image: QImage) -> None:
        """Store the latest coherent viewport image + its sensor-normalized rect (latest-wins by frame index)."""
        data = self._channel(channel)
        if data.source_stream_id != header.source_stream_id:
            data.viewport_frame_idx = -1
            data.source_stream_id = header.source_stream_id
        if header.frame_idx < data.viewport_frame_idx:
            return
        data.viewport_frame = image
        rect = header.source_rect_px
        data.viewport_rect = PreviewViewport(
            x=rect.x / header.sensor_width,
            y=rect.y / header.sensor_height,
            w=rect.width / header.sensor_width,
            h=rect.height / header.sensor_height,
        )
        data.viewport_frame_idx = header.frame_idx
        self.composite_updated.emit()

    def start_feed(self, instrument: Instrument) -> Teardown:
        """Consume the instrument's live preview streams (overview frames + viewport images, preview and
        acquisition alike). Clears stale data on preview-epoch bump so a previous profile's channels don't
        linger. Returns a teardown callable that detaches the subscriptions.
        """
        self._instrument = instrument
        unsubs = [
            instrument.frames.subscribe(self._on_frame),
            instrument.viewport_frames.subscribe(self._on_viewport_frame),
            instrument.preview_epoch.subscribe(lambda _e: self.clear_frames()),
        ]

        def teardown() -> None:
            for unsub in unsubs:
                unsub()
            self._instrument = None

        return teardown

    async def _on_frame(self, update: tuple[str, bytes]) -> None:
        # Decompress off the UI thread so the qasync loop remains responsive.
        channel, data = update
        header, image = await asyncio.get_running_loop().run_in_executor(None, _decode_image, data)
        self.set_frame(channel, image, header, self._rotation_for(channel))

    async def _on_viewport_frame(self, update: tuple[str, bytes]) -> None:
        # Decompress off the UI thread so the qasync loop remains responsive.
        channel, data = update
        header, image = await asyncio.get_running_loop().run_in_executor(None, _decode_image, data)
        self.set_viewport_frame(channel, header, image)

    def _rotation_for(self, channel: str) -> int:
        """The channel's camera rotation (deg) from its channel config + HAL config; 0 if unknown."""
        if self._instrument is None:
            return 0
        channel_config = self._instrument.state.value.imaging.channels.get(channel)
        if channel_config is None:
            return 0
        detection = self._instrument.hardware_config.detection.get(channel_config.detection)
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
