import asyncio
import logging
import math
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
from pydantic import Field
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
    """Visible region of the sensor in normalized coordinates [0, 1]."""

    x: float = Field(default=0.0, ge=0.0, le=1.0, description="Top-left X in normalized sensor coords.")
    y: float = Field(default=0.0, ge=0.0, le=1.0, description="Top-left Y in normalized sensor coords.")
    w: float = Field(default=1.0, gt=0.0, le=1.0, description="Viewport width in normalized sensor coords.")
    h: float = Field(default=1.0, gt=0.0, le=1.0, description="Viewport height in normalized sensor coords.")

    @property
    def needs_adjustment(self) -> bool:
        return self.w < 1.0 or self.h < 1.0


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
    fmt: PreviewFmt = Field(default=PreviewFmt.JPEG)
    colormap: str | None = Field(default=None, description="Colormap applied, or None for grayscale.")


class PreviewFrameInfo(PreviewInfoBase):
    """Overview frame metadata. Always sent, carries histogram."""

    histogram: list[int] | None = Field(
        default=None,
        description="1024-bin histogram of preview intensity. Only present in overview frames.",
    )


class PreviewTileInfo(PreviewInfoBase):
    """Single tile from the pyramid."""

    scale: int = Field(..., ge=0, description="Pyramid scale (0 = coarsest).")
    col: int = Field(..., ge=0, description="Tile column index at this scale.")
    row: int = Field(..., ge=0, description="Tile row index at this scale.")
    viewport: PreviewViewport = Field(..., description="Viewport that triggered this tile set.")


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


@dataclass(frozen=True)
class PreviewTile:
    info: PreviewTileInfo
    data: bytes

    @classmethod
    def from_array(cls, frame_array: np.ndarray, info: PreviewTileInfo) -> Self:
        """Create a PreviewTile from a NumPy array and metadata."""
        compressed_data = info.fmt(frame_array)
        return cls(info=info, data=compressed_data)

    @classmethod
    def from_packed(cls, packed_tile: bytes) -> Self:
        """Unpack a packed PreviewTile from bytes."""
        unpacked = msgpack.unpackb(packed_tile, object_hook=mpack_numpy.decode)
        info = PreviewTileInfo(**unpacked["info"])
        return cls(info=info, data=unpacked["data"])

    def pack(self) -> bytes:
        """Pack for transmission via msgpack."""
        packed = msgpack.packb(
            {"info": self.info.model_dump(), "data": self.data},
            default=mpack_numpy.encode,
        )
        if packed is None:
            raise ValueError("Packing PreviewTile failed: msgpack.packb returned None")
        return packed


# ── Sink Types ─────────────────────────────────────────────────────────

type PreviewFrameSink = Callable[[PreviewFrame], None]
type PreviewTileSink = Callable[[PreviewTile], Awaitable[None]]


# ── Tile Scale Selection ──────────────────────────────────────────────


MAX_SCALE = 6  # 64x64 grid max
DEFAULT_TILE_SIZE = 1024  # output pixels per tile


def select_scale(
    viewport: PreviewViewport,
    sensor_w: int,
    sensor_h: int,
    tile_size: int = DEFAULT_TILE_SIZE,
) -> int:
    """Pick pyramid scale for current viewport.

    Scale S means a 2^S x 2^S grid of tiles covering the full sensor.
    At scale S, each tile covers (sensor / 2^S) raw pixels per axis.

    The scale is chosen based on zoom level (viewport), capped by the finest
    scale where tiles still have enough raw data (determined by tile_size).
    """
    sensor_max = max(sensor_w, sensor_h)
    if sensor_max <= tile_size:
        return 0

    # Max scale: one level beyond strict no-upsample threshold.
    max_scale = min(MAX_SCALE, int(math.log2(sensor_max / tile_size)) + 1)

    # At full viewport (no zoom), scale 1 gives 2x2 tiles
    viewport_max = max(viewport.w, viewport.h)
    if viewport_max >= 1.0:
        return 1

    # Ideal scale from zoom level, prefer finer resolution (ceil)
    ideal = max(1, math.ceil(math.log2(1.0 / viewport_max)))
    return min(ideal, max_scale)


def compute_visible_tiles(
    viewport: PreviewViewport,
    scale: int,
    *,
    padding: int = 1,
) -> list[tuple[int, int]]:
    """Compute (col, row) indices of tiles that intersect the viewport, plus padding.

    Padding adds extra tiles around the viewport for panning headroom.
    """
    grid = 2**scale

    col_start = max(0, int(viewport.x * grid) - padding)
    col_end = min(grid, math.ceil((viewport.x + viewport.w) * grid) + padding)
    row_start = max(0, int(viewport.y * grid) - padding)
    row_end = min(grid, math.ceil((viewport.y + viewport.h) * grid) + padding)

    return [(col, row) for row in range(row_start, row_end) for col in range(col_start, col_end)]


# ── Preview Generator ─────────────────────────────────────────────────


class PreviewGenerator:
    """Generates overview frames and tiles from raw camera frames.

    Overview frames are always generated at `target_width` resolution with histogram.
    Tiles are generated at the appropriate pyramid scale for the current viewport,
    using parallel execution for throughput.
    """

    def __init__(
        self,
        frame_sink: PreviewFrameSink,
        tile_sink: PreviewTileSink | None = None,
        uid: str = "camera",
        *,
        target_width: int = 1024,
        tile_size: int = DEFAULT_TILE_SIZE,
        fmt: PreviewFmt = PreviewFmt.JPEG,
        viewport: PreviewViewport | None = None,
        levels: PreviewLevels | None = None,
    ) -> None:
        self._uid = uid
        self._frame_sink = frame_sink
        self._tile_sink = tile_sink
        self._target_width: int = target_width
        self._tile_size: int = tile_size
        self._fmt: PreviewFmt = fmt or PreviewFmt.JPEG
        self.viewport = viewport or PreviewViewport()
        self.levels = levels or PreviewLevels()
        self._idx: int = 0
        self._current_frame: np.ndarray | None = None
        self._colormap: str | None = None
        self._lut: np.ndarray | None = None  # (256, 3) uint8, cached
        self._tile_task: asyncio.Task | None = None  # background tile generation
        self.log = logging.getLogger(f"{self._uid}.PreviewGenerator")

        # Dedicated executor for overview (never competes with tiles)
        self._overview_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PreviewOverview")
        # Parallel executor for tile generation
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="PreviewTile")

    @property
    def colormap(self) -> str | None:
        """Colormap name applied to preview frames, or None for grayscale."""
        return self._colormap

    @colormap.setter
    def colormap(self, value: str | None) -> None:
        self._colormap = value
        self._lut = resolve_colormap(value) if value else None

    async def new_frame(self, frame: np.ndarray, idx: int) -> None:
        """Process a new raw frame: generate overview + tiles.

        Overview blocks (quick, carries histogram). Tiles are fired off as a
        background task so the preview loop can immediately grab the next frame.
        If tiles from the previous frame are still generating, they're cancelled.
        """
        self._idx = idx
        self._current_frame = frame
        loop = asyncio.get_event_loop()

        # Cancel stale tiles and start new ones concurrently with overview
        if self._tile_sink is not None:
            self.cancel_tile_task()
            self._tile_task = asyncio.create_task(self._generate_and_send_tiles(frame, idx, self.viewport))

        # Overview blocks (runs on dedicated executor, concurrent with tile threads)
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
            if self._tile_sink is not None:
                await self._generate_and_send_tiles(self._current_frame, self._idx, self.viewport)

    async def reprocess_viewport(self, viewport: PreviewViewport) -> None:
        """Regenerate tiles from cached raw frame for a new viewport.

        Called when the viewport changes between camera grabs, so the user
        gets updated tiles immediately without waiting for the next frame.
        """
        self.viewport = viewport
        if self._tile_sink is not None and self._current_frame is not None:
            await self._generate_and_send_tiles(self._current_frame, self._idx, viewport)

    def cancel_tile_task(self) -> None:
        """Cancel in-flight background tile generation."""
        if self._tile_task is not None and not self._tile_task.done():
            self._tile_task.cancel()
            self._tile_task = None

    def shutdown(self) -> None:
        """Shutdown the preview generator and cleanup resources."""
        self.cancel_tile_task()
        self._overview_executor.shutdown(wait=False, cancel_futures=True)
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ── Internal: Downsampling ─────────────────────────────────────────

    @staticmethod
    def _downsample(frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
        """Downsample a frame to target dimensions.

        For large downsample factors (>2x), pre-decimates via numpy stride
        skipping to reduce data volume before cv2.resize. This avoids reading
        the entire source array through DRAM — the strided view fits in cache.
        """
        h, w = frame.shape[:2]
        step = max(1, min(w // (target_w * 2), h // (target_h * 2)))
        if step > 1:
            frame = frame[::step, ::step]
        return cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

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
        hist_data = histogram.tolist()

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
            histogram=hist_data,
        )

        preview_frame = PreviewFrame.from_array(processed, info)

        gen_time = time.perf_counter() - gen_start
        if frame_idx < 5 or frame_idx % 100 == 0:
            self.log.debug(f"Overview frame {frame_idx}: {gen_time * 1000:.1f}ms")

        return preview_frame

    # ── Internal: Tiles ────────────────────────────────────────────────

    async def _generate_and_send_tiles(self, raw_frame: np.ndarray, frame_idx: int, viewport: PreviewViewport) -> None:
        """Generate visible tiles in parallel and send each as it completes."""
        full_height, full_width = raw_frame.shape[:2]
        scale = select_scale(viewport, full_width, full_height, self._tile_size)

        visible = compute_visible_tiles(viewport, scale)
        if not visible:
            return

        loop = asyncio.get_event_loop()
        tile_futures = [
            loop.run_in_executor(
                self._executor,
                self._generate_tile,
                raw_frame,
                frame_idx,
                viewport,
                scale,
                col,
                row,
            )
            for col, row in visible
        ]

        try:
            for coro in asyncio.as_completed(tile_futures):
                tile = await coro
                await self._tile_sink(tile)  # type: ignore[misc]
        except asyncio.CancelledError:
            return  # new frame arrived, abandon remaining tiles

    def _generate_tile(
        self,
        raw_frame: np.ndarray,
        frame_idx: int,
        viewport: PreviewViewport,
        scale: int,
        col: int,
        row: int,
    ) -> PreviewTile:
        """Generate a single tile (runs in thread pool)."""
        full_height, full_width = raw_frame.shape[:2]
        grid = 2**scale

        # Tile bounds in sensor pixels
        x0 = int(full_width * col / grid)
        y0 = int(full_height * row / grid)
        x1 = int(full_width * (col + 1) / grid)
        y1 = int(full_height * (row + 1) / grid)

        tile_region = raw_frame[y0:y1, x0:x1]
        region_w = x1 - x0
        region_h = y1 - y0

        # Resize: cap the wider dimension to tile_size, preserve aspect
        if region_w >= region_h:
            out_w = min(self._tile_size, region_w)
            out_h = max(1, int(out_w * region_h / region_w))
        else:
            out_h = min(self._tile_size, region_h)
            out_w = max(1, int(out_h * region_w / region_h))

        resized = self._downsample(tile_region, out_w, out_h)
        processed = self._apply_processing(resized, raw_frame.dtype)

        info = PreviewTileInfo(
            frame_idx=frame_idx,
            width=out_w,
            height=out_h,
            full_width=full_width,
            full_height=full_height,
            levels=self.levels,
            fmt=self._fmt,
            colormap=self._colormap,
            scale=scale,
            col=col,
            row=row,
            viewport=viewport,
        )

        return PreviewTile.from_array(processed, info)

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


def convert_to_jpeg(frame: np.ndarray, quality: int = 100) -> bytes:
    """Convert a NumPy array (BGR image) to JPEG-encoded bytes using OpenCV."""
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, encoded_image = cv2.imencode(".jpg", cast("cv2.UMat", frame), encode_params)
    if not success:
        raise RuntimeError("JPEG encoding failed")
    return encoded_image.tobytes()


def convert_to_png(frame: np.ndarray) -> bytes:
    """Convert a NumPy array (BGR image) to PNG-encoded bytes using OpenCV."""
    encode_params = [int(cv2.IMWRITE_PNG_COMPRESSION), 0]
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
