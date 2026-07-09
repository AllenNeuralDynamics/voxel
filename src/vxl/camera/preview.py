import asyncio
import logging
import time
import zlib
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, cast

import cv2
import msgpack
import msgpack_numpy as mpack_numpy
import numpy as np
from pydantic import Field, field_validator
from vxlib.color import resolve_colormap

from vxlib import SchemaModel


class PreviewFmt(StrEnum):
    RAW = "raw"
    JPEG = "jpeg"
    PNG = "png"
    ZLIB = "zlib"

    def __call__(self, frame: np.ndarray) -> bytes:
        match self:
            case PreviewFmt.RAW:
                return convert_to_raw(frame)
            case PreviewFmt.JPEG:
                return convert_to_jpeg(frame)
            case PreviewFmt.PNG:
                return convert_to_png(frame)
            case PreviewFmt.ZLIB:
                return compress_uint16_frame_zlib(frame)


# ── Viewport & Levels ──────────────────────────────────────────────────


class PreviewViewport(SchemaModel):
    """Visible region in normalized coordinates [0, 1].

    When sent from the frontend, coordinates are stage-normalized.
    The rig inverse-rotates per camera to produce sensor-normalized viewports.
    Origin values are clamped to absorb floating-point drift from arithmetic
    like ``1 - x - w``.
    """

    x: float = Field(default=0.0, description="Top-left X in normalized coords.")
    y: float = Field(default=0.0, description="Top-left Y in normalized coords.")
    w: float = Field(default=1.0, gt=0.0, le=1.0, description="Viewport width in normalized coords.")
    h: float = Field(default=1.0, gt=0.0, le=1.0, description="Viewport height in normalized coords.")

    @field_validator("x", "y", mode="before")
    @classmethod
    def _clamp_origin(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @property
    def needs_adjustment(self) -> bool:
        return self.w < 1.0 or self.h < 1.0

    def to_sensor_space(self, rotation_deg: int) -> "PreviewViewport":
        """Inverse-rotate a stage-normalized viewport into sensor-normalized coords.

        For 0°/180° the footprint shape is unchanged (only origin flips).
        For 90°/270° width and height swap, and origin re-anchors.
        """
        r = rotation_deg % 360
        if r == 0:
            return self
        if r == 90:
            return PreviewViewport(x=self.y, y=1 - self.x - self.w, w=self.h, h=self.w)
        if r == 180:
            return PreviewViewport(x=1 - self.x - self.w, y=1 - self.y - self.h, w=self.w, h=self.h)
        if r == 270:
            return PreviewViewport(x=1 - self.y - self.h, y=self.x, w=self.h, h=self.w)
        return self

    def expanded(self, margin: float) -> "PreviewViewport":
        """Grow the rect by `margin` (fraction of each axis) about its center, clamped to [0, 1]."""
        if margin <= 0.0:
            return self
        nw = min(1.0, self.w * (1.0 + 2.0 * margin))
        nh = min(1.0, self.h * (1.0 + 2.0 * margin))
        cx = self.x + self.w / 2.0
        cy = self.y + self.h / 2.0
        nx = max(0.0, min(cx - nw / 2.0, 1.0 - nw))
        ny = max(0.0, min(cy - nh / 2.0, 1.0 - nh))
        return PreviewViewport(x=nx, y=ny, w=nw, h=nh)


class PreviewLevels(SchemaModel):
    min: float = Field(default=0.0, ge=0.0, le=1.0, description="black point of the preview")
    max: float = Field(default=1.0, ge=0.0, le=1.0, description="white point of the preview")

    @property
    def needs_adjustment(self) -> bool:
        return self.min != 0.0 or self.max != 1.0

    @classmethod
    def from_histogram(cls, histogram: list[int], percentile: float = 1.0) -> Self:
        """Calculate auto-levels from a histogram using percentile clipping.

        Args:
            histogram: Histogram bin counts (any number of bins)
            percentile: Percentile to clip at low/high ends (default 1.0 means 1st and 99th percentile)

        Returns:
            PreviewLevels with min/max normalized to 0-1 range
        """
        total = sum(histogram)
        if total == 0:
            return cls()

        low_threshold = total * (percentile / 100.0)
        high_threshold = total * ((100.0 - percentile) / 100.0)

        # Find low percentile bin
        cumsum = 0
        low_bin = 0
        for i, count in enumerate(histogram):
            cumsum += count
            if cumsum >= low_threshold:
                low_bin = i
                break

        # Find high percentile bin
        cumsum = 0
        high_bin = len(histogram) - 1
        for i, count in enumerate(histogram):
            cumsum += count
            if cumsum >= high_threshold:
                high_bin = i
                break

        # Normalize to 0-1 range
        num_bins = len(histogram)
        min_val = low_bin / (num_bins - 1)
        max_val = high_bin / (num_bins - 1)

        # Ensure min < max
        if max_val <= min_val:
            max_val = min_val + 0.01

        return cls(min=min_val, max=max_val)


class PreviewConfig(SchemaModel):
    """Current preview display configuration for a camera."""

    viewport: PreviewViewport = Field(default_factory=PreviewViewport)
    levels: PreviewLevels = Field(default_factory=PreviewLevels)
    colormap: str | None = None


# ── Frame & Tile Info Models ───────────────────────────────────────────


class PreviewInfoBase(SchemaModel):
    """Fields shared by overview frames and tiles."""

    frame_idx: int = Field(..., ge=0, description="Frame index of the captured image.")
    width: int = Field(..., gt=0, description="Output pixel width.")
    height: int = Field(..., gt=0, description="Output pixel height.")
    full_width: int = Field(..., gt=0, description="Full sensor width in pixels.")
    full_height: int = Field(..., gt=0, description="Full sensor height in pixels.")
    levels: PreviewLevels = Field(default_factory=PreviewLevels)
    fmt: PreviewFmt = Field(default=PreviewFmt.PNG)
    colormap: str | None = Field(default=None, description="Colormap applied, or None for grayscale.")


class PreviewFrameInfo(PreviewInfoBase):
    """Overview / viewport-image metadata. Carries the rendered region and (overview only) a histogram."""

    rect: PreviewViewport = Field(
        default_factory=PreviewViewport,
        description="Server-rendered region (incl. overscan) in sensor-normalized coords; full frame for the overview.",
    )
    histogram: list[int] | None = Field(
        default=None,
        description="1024-bin histogram of preview intensity. Only present in overview frames.",
    )


# ── Data Containers ────────────────────────────────────────────────────


@dataclass(frozen=True)
class PreviewFrame:
    info: PreviewFrameInfo
    data: bytes

    @classmethod
    def from_array(cls, frame_array: np.ndarray, info: PreviewFrameInfo) -> Self:
        """Create a PreviewFrame from a NumPy array and metadata."""
        compressed_data = info.fmt(frame_array)
        return cls(info=info, data=compressed_data)

    @classmethod
    def from_packed(cls, packed_frame: bytes) -> Self:
        """Unpack a packed PreviewFrame from bytes."""
        unpacked = msgpack.unpackb(packed_frame, object_hook=mpack_numpy.decode)
        info_dict = unpacked.get("info") or unpacked.get("metadata")
        frame_data: bytes = unpacked.get("data") or unpacked.get("frame")
        if info_dict is None or frame_data is None:
            raise ValueError(f"Invalid packed frame format: {unpacked.keys()}")
        info = PreviewFrameInfo(**info_dict)
        return cls(info=info, data=frame_data)

    def pack(self) -> bytes:
        """Pack for transmission via msgpack."""
        packed = msgpack.packb(
            {"info": self.info.model_dump(), "data": self.data},
            default=mpack_numpy.encode,
        )
        if packed is None:
            raise ValueError("Packing PreviewFrame failed: msgpack.packb returned None")
        return packed


# ── Sink Types ─────────────────────────────────────────────────────────

type PreviewFrameSink = Callable[["PreviewFrame"], None]
type PreviewViewSink = Callable[[bytes], Awaitable[None]]


# ── Render sizing ─────────────────────────────────────────────────────


DEFAULT_PREVIEW_WIDTH = 2048  # overview output width
RENDER_CAP = DEFAULT_PREVIEW_WIDTH  # max width of a single coherent viewport-image render
OVERSCAN_MARGIN = 0.25  # fraction each axis grows beyond the viewport, so small pans stay covered (tunable)


# ── Preview Generator ─────────────────────────────────────────────────


class PreviewGenerator:
    """Generates the overview frame and the zoomed viewport image from raw camera frames.

    The overview is always generated at `target_width` with a histogram. The viewport image is one
    coherent crop (expanded by overscan) at the display resolution, replacing the old pyramid tiles.
    """

    def __init__(
        self,
        frame_sink: PreviewFrameSink,
        view_sink: PreviewViewSink | None = None,
        uid: str = "camera",
        *,
        target_width: int = DEFAULT_PREVIEW_WIDTH,
        fmt: PreviewFmt = PreviewFmt.PNG,
        viewport: PreviewViewport | None = None,
        levels: PreviewLevels | None = None,
    ) -> None:
        self._uid = uid
        self._frame_sink = frame_sink
        # The zoomed detail layer is one coherent viewport image (preview_view via view_sink).
        self._view_sink = view_sink
        self._target_width: int = target_width
        self._fmt: PreviewFmt = fmt
        self.viewport = viewport or PreviewViewport()
        self.levels = levels or PreviewLevels()
        self._idx: int = 0
        self._current_frame: np.ndarray | None = None
        self._last_histogram: list[int] | None = None  # most recent overview histogram, for auto-leveling
        self._colormap: str | None = None
        self._lut: np.ndarray | None = None  # (256, 3) uint8, cached
        self._view_task: asyncio.Task | None = None  # background viewport-image generation
        self._view_futures: list[asyncio.Future] = []  # tracked for cancellation
        self._overview_task: asyncio.Task | None = None  # background overview generation
        self.log = logging.getLogger(f"{self._uid}.PreviewGenerator")

        # Dedicated executor for overview (never competes with the viewport render)
        self._overview_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PreviewOverview")
        # Executor for the viewport-image crop/resample/encode
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="PreviewView")

    @property
    def last_histogram(self) -> list[int] | None:
        """Histogram of the most recent overview frame (pre-level-adjustment), or None before any frame."""
        return self._last_histogram

    @property
    def colormap(self) -> str | None:
        """Colormap name applied to preview frames, or None for grayscale."""
        return self._colormap

    @colormap.setter
    def colormap(self, value: str | None) -> None:
        self._colormap = value
        self._lut = resolve_colormap(value) if value else None

    async def new_frame(self, frame: np.ndarray, idx: int) -> None:
        """Process a new raw frame: dispatch overview + tiles as background tasks.

        Tiles use cancel-stale (latest viewport invalidates prior work). Overview
        uses skip-if-busy — if the previous overview hasn't finished, drop this
        frame's preview rather than queueing. Returns immediately so callers
        (preview loop, acquisition grab loop) are not gated by preview work.
        """
        self._idx = idx
        self._current_frame = frame

        if self._view_sink is not None:
            self.cancel_view_task()
            self._view_task = asyncio.create_task(self._generate_and_send_view(frame, idx, self.viewport))

        if self._overview_task is None or self._overview_task.done():
            self._overview_task = asyncio.create_task(self._run_overview(frame, idx))

    async def _run_overview(self, frame: np.ndarray, idx: int) -> None:
        loop = asyncio.get_event_loop()
        overview = await loop.run_in_executor(self._overview_executor, self._generate_overview, frame, idx)
        self._frame_sink(overview)

    async def reprocess(self) -> None:
        """Regenerate overview + tiles from cached raw frame with current settings.

        Useful for applying levels/colormap changes without waiting for the next camera grab,
        including when preview is stopped.
        """
        if self._current_frame is not None:
            loop = asyncio.get_event_loop()
            frame, idx = self._current_frame, self._idx
            overview = await loop.run_in_executor(self._overview_executor, self._generate_overview, frame, idx)
            self._frame_sink(overview)
            if self._view_sink is not None:
                await self._generate_and_send_view(frame, idx, self.viewport)

    async def reprocess_viewport(self, viewport: PreviewViewport) -> None:
        """Regenerate tiles from cached raw frame for a new viewport.

        Called when the viewport changes between camera grabs, so the user
        gets updated tiles immediately without waiting for the next frame.
        """
        self.viewport = viewport
        if self._current_frame is not None and self._view_sink is not None:
            await self._generate_and_send_view(self._current_frame, self._idx, viewport)

    def clear_cache(self) -> None:
        """Clear cached raw frame. Called on profile change to prevent stale reprocessing."""
        self._current_frame = None

    def cancel_view_task(self) -> None:
        """Cancel in-flight background viewport-image generation and pending executor futures."""
        if self._view_task is not None and not self._view_task.done():
            self._view_task.cancel()
            self._view_task = None
        for f in self._view_futures:
            f.cancel()
        self._view_futures.clear()

    def shutdown(self) -> None:
        """Shutdown the preview generator and cleanup resources."""
        self.cancel_view_task()
        if self._overview_task is not None and not self._overview_task.done():
            self._overview_task.cancel()
        self._overview_task = None
        self._overview_executor.shutdown(wait=False, cancel_futures=True)
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ── Internal: Downsampling ─────────────────────────────────────────

    @staticmethod
    def _downsample(frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
        """Downsample a frame to approximately target dimensions.

        TEST: stride-only downsampling (no cv2.resize). Skips directly to ~target
        size via numpy stride view (O(1), no memory read). Output dimensions are
        approximate (nearest integer stride). The frontend's drawImage scales to
        canvas anyway so exact dimensions don't matter.

        This eliminates the cv2.resize bottleneck entirely. Quality is nearest-
        neighbor (no anti-aliasing) but acceptable for live preview.
        """
        h, w = frame.shape[:2]
        step_w = max(1, w // target_w)
        step_h = max(1, h // target_h)
        step = max(step_w, step_h)  # uniform step preserves aspect ratio
        return np.ascontiguousarray(frame[::step, ::step])

        # ORIGINAL: two-step with cv2.resize for final anti-aliased downsample
        # h, w = frame.shape[:2]
        # step = max(1, min(w // (target_w * 2), h // (target_h * 2)))
        # if step > 1:
        #     frame = frame[::step, ::step]
        # return cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

    # ── Internal: Overview ─────────────────────────────────────────────

    def _generate_overview(self, raw_frame: np.ndarray, frame_idx: int) -> PreviewFrame:
        """Generate the overview frame: full sensor downsampled to target_width with histogram."""
        gen_start = time.perf_counter()

        full_height, full_width = raw_frame.shape[:2]
        preview_width = self._target_width
        preview_height = int(full_height * (preview_width / full_width))

        resized = self._downsample(raw_frame, preview_width, preview_height)

        # Compute histogram on resized data BEFORE level adjustment
        max_val = np.iinfo(raw_frame.dtype).max
        num_bins = 1024
        histogram, _ = np.histogram(resized, bins=num_bins, range=(0, max_val))
        self._last_histogram = histogram.tolist()

        # Apply levels + colormap
        processed = self._apply_processing(resized, raw_frame.dtype)

        info = PreviewFrameInfo(
            frame_idx=frame_idx,
            width=preview_width,
            height=preview_height,
            full_width=full_width,
            full_height=full_height,
            levels=self.levels,
            fmt=self._fmt,
            colormap=self._colormap,
            histogram=self._last_histogram,
        )

        preview_frame = PreviewFrame.from_array(processed, info)

        gen_time = time.perf_counter() - gen_start
        if frame_idx < 5 or frame_idx % 100 == 0:
            self.log.debug(f"Overview frame {frame_idx}: {gen_time * 1000:.1f}ms")

        return preview_frame

    # ── Internal: Viewport image ───────────────────────────────────────

    async def _generate_and_send_view(self, raw_frame: np.ndarray, frame_idx: int, viewport: PreviewViewport) -> None:
        """Render the zoomed viewport as one coherent image and send it.

        No-op at a full (unzoomed) viewport: the overview frame already covers it. Latest-wins —
        `cancel_view_task` supersedes any in-flight render whose viewport is already stale.
        """
        if not viewport.needs_adjustment:
            return
        loop = asyncio.get_event_loop()
        fut = loop.run_in_executor(self._executor, self._generate_view, raw_frame, frame_idx, viewport)
        self._view_futures = [fut]
        try:
            view = await fut
        except asyncio.CancelledError:
            return
        finally:
            self._view_futures = []
        packed = await loop.run_in_executor(self._executor, view.pack)
        if self._view_sink is not None:
            await self._view_sink(packed)

    def _generate_view(self, raw_frame: np.ndarray, frame_idx: int, viewport: PreviewViewport) -> PreviewFrame:
        """Crop the viewport (expanded by overscan), resample once to <= RENDER_CAP, process once, encode once."""
        full_height, full_width = raw_frame.shape[:2]
        rect = viewport.expanded(OVERSCAN_MARGIN)

        x0 = max(0, min(int(rect.x * full_width), full_width - 1))
        y0 = max(0, min(int(rect.y * full_height), full_height - 1))
        x1 = max(x0 + 1, min(int((rect.x + rect.w) * full_width), full_width))
        y1 = max(y0 + 1, min(int((rect.y + rect.h) * full_height), full_height))

        crop = raw_frame[y0:y1, x0:x1]
        crop_w = x1 - x0
        crop_h = y1 - y0

        out_w = min(crop_w, RENDER_CAP)
        out_h = max(1, round(crop_h * out_w / crop_w))
        resized = self._downsample(crop, out_w, out_h)
        processed = self._apply_processing(resized, raw_frame.dtype)

        rh, rw = resized.shape[:2]
        info = PreviewFrameInfo(
            frame_idx=frame_idx,
            width=rw,
            height=rh,
            full_width=full_width,
            full_height=full_height,
            levels=self.levels,
            fmt=self._fmt,
            colormap=self._colormap,
            rect=rect,
            histogram=None,
        )
        return PreviewFrame.from_array(processed, info)

    # ── Internal: Shared Processing ────────────────────────────────────

    def _apply_processing(self, frame: np.ndarray, src_dtype: np.dtype) -> np.ndarray:
        """Apply levels + colormap to a resized frame. Returns uint8 (or BGR if colormap)."""
        max_val = np.iinfo(src_dtype).max
        preview_float = frame.astype(np.float32) / max_val

        levels = self.levels
        if levels.needs_adjustment:
            preview_float = np.clip(preview_float, levels.min, levels.max)
            denom = (levels.max - levels.min) + 1e-8
            preview_float = (preview_float - levels.min) / denom

        preview_float *= 255.0
        preview_uint8 = preview_float.astype(np.uint8)

        if self._lut is not None:
            return cv2.cvtColor(self._lut[preview_uint8], cv2.COLOR_RGB2BGR)
        return preview_uint8


# ── Encoding Functions ─────────────────────────────────────────────────

# PNG (zlib) compression level for preview encodes. Benchmarked at 2048²: level 1 is already at the
# size floor (level 9 saves only ~3%) at ~1/2 the encode time, so higher levels aren't worth the latency.
PNG_COMPRESSION = 1


def convert_to_jpeg(frame: np.ndarray, quality: int = 100) -> bytes:
    """Convert a NumPy array (BGR image) to JPEG-encoded bytes using OpenCV."""
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, encoded_image = cv2.imencode(".jpg", cast("cv2.UMat", frame), encode_params)
    if not success:
        raise RuntimeError("JPEG encoding failed")
    return encoded_image.tobytes()


def convert_to_png(frame: np.ndarray, compression: int = PNG_COMPRESSION) -> bytes:
    """Convert a NumPy array (BGR image) to lossless PNG-encoded bytes using OpenCV.

    `compression` is the zlib level 0-9 (higher = smaller + slower); the default trades near-minimal
    size for low encode latency.
    """
    encode_params = [int(cv2.IMWRITE_PNG_COMPRESSION), compression]
    success, encoded_image = cv2.imencode(".png", frame, encode_params)
    if not success:
        raise RuntimeError("PNG encoding failed")
    return encoded_image.tobytes()


def convert_to_raw(frame: np.ndarray) -> bytes:
    """Return the raw bytes of the NumPy array without any compression or encoding."""
    return frame.tobytes()


def compress_uint16_frame_zlib(frame: np.ndarray) -> bytes:
    """Compress a 2D (or 3D) NumPy array of dtype=uint16 with zlib."""
    if not frame.flags["C_CONTIGUOUS"]:
        frame = np.ascontiguousarray(frame)
    raw_bytes = frame.tobytes()
    return zlib.compress(raw_bytes, level=9)
