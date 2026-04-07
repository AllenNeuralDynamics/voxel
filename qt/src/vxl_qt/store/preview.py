"""Preview state store and compositing functions.

This module provides:
- Pure functions for frame compositing (blend, crop, resize, blur)
- PreviewStore for managing preview state (frames, viewport, interaction)
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter
from PySide6.QtCore import QObject, Signal

from vxl.camera.preview import PreviewLevels, PreviewViewport


def composite_rgb(frames: list[np.ndarray]) -> np.ndarray | None:
    """Additively blend RGB frames.

    Args:
        frames: List of RGB images (H, W, 3) to blend

    Returns:
        Blended RGB image, or None if no frames
    """
    if not frames:
        return None

    target_shape = frames[0].shape[:2]
    height, width = target_shape

    # Accumulate in uint16 to avoid overflow
    result = np.zeros((height, width, 3), dtype=np.uint16)

    for frame in frames:
        # Resize if needed
        if frame.shape[:2] != target_shape:
            pil_img = Image.fromarray(frame)
            pil_img = pil_img.resize((width, height), Image.Resampling.NEAREST)
            resized = np.array(pil_img)
            result += resized.astype(np.uint16)
        else:
            result += frame.astype(np.uint16)

    return np.clip(result, 0, 255).astype(np.uint8)


def crop_image(image: np.ndarray, viewport: PreviewViewport) -> np.ndarray:
    """Crop an image using a viewport in normalized coordinates.

    Args:
        image: Input image (H, W) or (H, W, C)
        viewport: Viewport with x, y (top-left) and w, h (size), all in [0, 1]

    Returns:
        Cropped image
    """
    if viewport.w >= 1.0 and viewport.h >= 1.0:
        return image

    height, width = image.shape[:2]

    x0 = int(viewport.x * width)
    y0 = int(viewport.y * height)
    x1 = int((viewport.x + viewport.w) * width)
    y1 = int((viewport.y + viewport.h) * height)

    # Clamp to valid bounds
    x0 = max(0, min(x0, width - 1))
    y0 = max(0, min(y0, height - 1))
    x1 = max(x0 + 1, min(x1, width))
    y1 = max(y0 + 1, min(y1, height))

    return image[y0:y1, x0:x1]


def blur_image(image: np.ndarray, radius: float = 1.0) -> np.ndarray:
    """Apply Gaussian blur to an image."""
    pil_img = Image.fromarray(image)
    pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=radius))
    return np.array(pil_img)


def resize_image(image: np.ndarray, target_width: int) -> np.ndarray:
    """Resize image to target width, maintaining aspect ratio."""
    height, width = image.shape[:2]
    if width == target_width:
        return image
    target_height = int(height * target_width / width)
    pil_img = Image.fromarray(image)
    pil_img = pil_img.resize((target_width, target_height), Image.Resampling.BILINEAR)
    return np.array(pil_img)


@dataclass
class ChannelData:
    """Frame data for a single channel.

    Stores the latest overview frame (full sensor, downsampled).
    Histogram is only present on overview frames.
    """

    frame: np.ndarray  # Overview frame (H, W, 3), always present
    colormap: str | None = None
    histogram: list[int] | None = None

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

    def set_frame(
        self,
        channel: str,
        data: np.ndarray,
        colormap: str | None = None,
        histogram: list[int] | None = None,
    ) -> None:
        """Store an overview frame for a channel."""
        self._channels[channel] = ChannelData(
            frame=data,
            colormap=colormap,
            histogram=histogram,
        )
        self.frame_received.emit(channel)
        self.composite_updated.emit()

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
