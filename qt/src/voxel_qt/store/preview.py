"""Preview state store and compositing functions.

This module provides:
- Pure functions for frame compositing (blend, crop, resize, blur)
- PreviewStore for managing preview state (frames, crop, interaction)
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter
from PySide6.QtCore import QObject, Signal

from voxel.camera.preview import PreviewCrop, PreviewLevels


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


def crop_image(image: np.ndarray, crop: PreviewCrop) -> np.ndarray:
    """Crop an image using normalized coordinates.

    Args:
        image: Input image (H, W) or (H, W, C)
        crop: Crop with x, y (top-left) and k (zoom factor, 0=none, 1=max)

    Returns:
        Cropped image
    """
    if crop.k <= 0:
        return image

    view_size = 1.0 - crop.k
    height, width = image.shape[:2]

    x0 = int(crop.x * width)
    y0 = int(crop.y * height)
    x1 = int((crop.x + view_size) * width)
    y1 = int((crop.y + view_size) * height)

    # Clamp to valid bounds
    x0 = max(0, min(x0, width - 1))
    y0 = max(0, min(y0, height - 1))
    x1 = max(x0 + 1, min(x1, width))
    y1 = max(y0 + 1, min(y1, height))

    return image[y0:y1, x0:x1]


def compute_local_crop(frame_crop: PreviewCrop, target_crop: PreviewCrop) -> PreviewCrop:
    """Compute local crop to apply to a frame.

    When the frame has a different crop than the target view, we need to
    compute a local crop that extracts the target region from the frame.

    Args:
        frame_crop: The crop that was applied server-side to produce this frame
        target_crop: The crop we want to display

    Returns:
        Local crop to apply to the frame image
    """
    if target_crop.k <= 0:
        return PreviewCrop()

    frame_view = 1.0 - frame_crop.k
    target_view = 1.0 - target_crop.k

    if frame_view <= 0:
        return PreviewCrop()

    # Calculate where target falls within frame (relative coords)
    rel_x = (target_crop.x - frame_crop.x) / frame_view
    rel_y = (target_crop.y - frame_crop.y) / frame_view
    rel_size = target_view / frame_view

    # Clamp
    rel_size = min(rel_size, 1.0)
    rel_x = max(0.0, min(rel_x, 1.0 - rel_size))
    rel_y = max(0.0, min(rel_y, 1.0 - rel_size))

    return PreviewCrop(x=rel_x, y=rel_y, k=1.0 - rel_size)


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

    Stores two frame slots:
    - frame: Latest full preview (always arrives, whole sensor view)
    - detail: Latest server-cropped preview + its crop metadata, or None when not zoomed

    Consumers pick which slot to read based on zoom/interaction state.
    Histogram is only present on full frames.
    """

    frame: np.ndarray  # Full preview (H, W, 3), always present
    detail: tuple[np.ndarray, PreviewCrop] | None = None  # (cropped_image, applied_crop) or None
    colormap: str | None = None
    histogram: list[int] | None = None

    def levels(self, percentile: float = 1.0) -> PreviewLevels:
        """Calculate auto-levels from histogram."""
        if self.histogram is None:
            return PreviewLevels()
        return PreviewLevels.from_histogram(self.histogram, percentile)


class PreviewStore(QObject):
    """Manages preview state: frames, crop, and interaction."""

    frame_received = Signal(str)  # channel_id
    crop_changed = Signal(float, float, float)  # x, y, k
    composite_updated = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._channels: dict[str, ChannelData] = {}
        self._crop = PreviewCrop()
        self._is_interacting = False

    @property
    def crop(self) -> PreviewCrop:
        """Current target crop/zoom state."""
        return self._crop

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
        crop: PreviewCrop,
        colormap: str | None = None,
        histogram: list[int] | None = None,
    ) -> None:
        """Store a frame for a channel.

        Routes to the correct slot based on crop:
        - Full frames (crop.k == 0): update frame, histogram, colormap
        - Cropped frames (crop.k > 0): update detail tuple
        """
        existing = self._channels.get(channel)
        is_full_frame = crop.k == 0

        if is_full_frame:
            self._channels[channel] = ChannelData(
                frame=data,
                detail=existing.detail if existing else None,
                colormap=colormap,
                histogram=histogram,
            )
        else:
            if existing is None:
                return  # no full frame yet, ignore detail
            existing.detail = (data, crop)
            existing.colormap = colormap

        self.frame_received.emit(channel)
        self.composite_updated.emit()

    def set_crop(self, crop: PreviewCrop) -> None:
        """Update the target crop/zoom state.

        Clears stale detail frames so consumers fall back to full frame
        with client-side local crop until fresh detail arrives.
        """
        self._crop = crop
        for ch in self._channels.values():
            ch.detail = None
        self.crop_changed.emit(crop.x, crop.y, crop.k)
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
        """Clear channel frame data, preserving crop/zoom viewport."""
        self._channels.clear()
        self._is_interacting = False
        self.composite_updated.emit()

    def reset(self) -> None:
        """Clear all state including crop/zoom viewport."""
        self._channels.clear()
        self._crop = PreviewCrop()
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
