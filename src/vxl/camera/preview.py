import asyncio
import logging
import time
import zlib
from collections.abc import Callable
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


class PreviewCrop(SchemaModel):
    x: float = Field(default=0.0, ge=0.0, le=1.0, description="normalized X coordinate of the preview.")
    y: float = Field(default=0.0, ge=0.0, le=1.0, description="normalized Y coordinate of the preview.")
    k: float = Field(default=0.0, ge=0.0, le=1.0, description="zoom factor - 0.0 no zoom, 1.0 full zoom.")

    @property
    def needs_adjustment(self) -> bool:
        return self.k != 0.0


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

    crop: PreviewCrop = Field(default_factory=PreviewCrop)
    levels: PreviewLevels = Field(default_factory=PreviewLevels)
    colormap: str | None = None


class PreviewFrameInfo(SchemaModel):
    """Contains the preview configuration settings for a frame including the config used to generate it."""

    frame_idx: int = Field(..., ge=0, description="Frame index of the captured image.")
    preview_width: int = Field(default=1024, gt=256, description="Target preview width in pixels.")
    preview_height: int = Field(..., gt=0, description="Target preview height in pixels.")
    full_width: int = Field(..., gt=0, description="Full image width in pixels (from captured frame).")
    full_height: int = Field(..., gt=0, description="Full image height in pixels (from captured frame).")
    crop: PreviewCrop = Field(default_factory=PreviewCrop)
    levels: PreviewLevels = Field(default_factory=PreviewLevels)
    fmt: PreviewFmt = Field(default=PreviewFmt.JPEG)
    histogram: list[int] | None = Field(
        default=None,
        description="256-bin histogram of preview intensity (0-255). Only present in full (non-cropped) frames.",
    )
    colormap: str | None = Field(
        default=None,
        description="Colormap applied to this frame, or None for grayscale.",
    )


@dataclass(frozen=True)
class PreviewFrame:
    info: PreviewFrameInfo
    data: bytes

    @classmethod
    def from_array(cls, frame_array: np.ndarray, info: PreviewFrameInfo) -> Self:
        """Create a PreviewFrame from a NumPy array and metadata.
        The frame is compressed using the specified compression method in metadata.
        """
        compressed_data = info.fmt(frame_array)
        return cls(info=info, data=compressed_data)

    @classmethod
    def from_packed(cls, packed_frame: bytes) -> Self:
        """Unpack a packed PreviewFrame from bytes.
        Returns a new PreviewFrame instance with the decompressed frame data.

        Supports both old ('metadata'/'frame') and new ('info'/'data') field names.
        """
        unpacked = msgpack.unpackb(packed_frame, object_hook=mpack_numpy.decode)

        # Support both old and new field names for backwards compatibility
        info_dict = unpacked.get("info") or unpacked.get("metadata")
        frame_data: bytes = unpacked.get("data") or unpacked.get("frame")

        if info_dict is None or frame_data is None:
            raise ValueError(f"Invalid packed frame format: {unpacked.keys()}")

        info = PreviewFrameInfo(**info_dict)
        return cls(info=info, data=frame_data)

    def pack(self) -> bytes:
        """Pack the PreviewFrame into a bytes representation for transmission or storage.
        Uses 'info' and 'data' field names to match the dataclass structure.
        """
        packed = msgpack.packb(
            {"info": self.info.model_dump(), "data": self.data},
            default=mpack_numpy.encode,
        )
        if packed is None:
            raise ValueError("Packing PreviewFrame failed: msgpack.packb returned None")
        return packed


type PreviewFrameSink = Callable[[PreviewFrame], None]


class PreviewGenerator:
    def __init__(
        self,
        sink: PreviewFrameSink,
        uid: str = "camera",
        *,
        target_width: int = 1024,
        fmt: PreviewFmt = PreviewFmt.JPEG,
        crop: PreviewCrop | None = None,
        levels: PreviewLevels | None = None,
    ) -> None:
        self._uid = uid
        self._sink = sink
        self._target_width: int = target_width
        self._fmt: PreviewFmt = fmt or PreviewFmt.JPEG
        self.crop = crop or PreviewCrop()
        self.levels = levels or PreviewLevels()
        self._idx: int = 0
        self._current_frame: np.ndarray | None = None
        self._colormap: str | None = None
        self._lut: np.ndarray | None = None  # (256, 3) uint8, cached
        self.log = logging.getLogger(f"{self._uid}.PreviewGenerator")

        # Dedicated executor for preview processing (1 worker per camera)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PreviewGenerator")

    @property
    def colormap(self) -> str | None:
        """Colormap name applied to preview frames, or None for grayscale."""
        return self._colormap

    @colormap.setter
    def colormap(self, value: str | None) -> None:
        self._colormap = value
        self._lut = resolve_colormap(value) if value else None

    async def new_frame(self, frame: np.ndarray, idx: int) -> None:
        """Set a new frame for previewing (async version - offloads processing to executor).

        This is the default/preferred method as it offloads expensive processing
        (resize, encoding) to a dedicated executor to avoid blocking.

        Processing (resize, encode) happens in executor thread, then sink is called
        from async context to avoid event loop issues with async ZMQ sockets.
        """
        self._idx = idx
        self._current_frame = frame

        # Offload expensive processing to executor to avoid blocking
        loop = asyncio.get_event_loop()

        # Generate full frame preview (processing in executor, then sink in async context)
        preview_frame = await loop.run_in_executor(self._executor, self._generate_preview_frame, frame, idx, False)
        self._sink(preview_frame)

        # if display options are set, generate and publish an optimized preview
        if self.crop.needs_adjustment or self.levels.needs_adjustment:
            preview_frame = await loop.run_in_executor(self._executor, self._generate_preview_frame, frame, idx, True)
            self._sink(preview_frame)

    def new_frame_sync(self, frame: np.ndarray, idx: int) -> None:
        """Set a new frame for previewing (synchronous version - blocks until complete).

        Use this only when you need synchronous processing or are not in an async context.
        For better performance in async code, use new_frame() instead.
        """
        self._idx = idx
        self._current_frame = frame

        def _sink_frame(adjust: bool = False) -> None:
            preview_frame = self._generate_preview_frame(raw_frame=frame, frame_idx=idx, adjust=adjust)
            self._sink(preview_frame)

        # send full frame to observers
        _sink_frame(adjust=False)

        # if display options are set, publish an optimized preview
        if self.crop.needs_adjustment or self.levels.needs_adjustment:
            _sink_frame(adjust=True)

    def shutdown(self) -> None:
        """Shutdown the preview generator and cleanup resources."""
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _generate_preview_frame(self, raw_frame: np.ndarray, frame_idx: int, adjust: bool = False) -> PreviewFrame:
        """Generate a PreviewFrame from the raw frame using the current preview_settings.
        The method crops the raw frame to the ROI (using normalized coordinates) and then
        resizes the cropped image to the target preview dimensions. It also applies black/white
        point and gamma adjustments to produce an 8-bit preview.
        """
        gen_start = time.perf_counter()

        full_width = raw_frame.shape[1]
        full_height = raw_frame.shape[0]
        preview_width = self._target_width
        preview_height = int(full_height * (preview_width / full_width))

        # 1) Compute absolute Crop coordinates.
        resize_start = time.perf_counter()
        if adjust:
            zoom = 1 - self.crop.k  # for k 0.0 is no zoom, 1.0 is full zoom
            crop_x0 = int(full_width * self.crop.x)
            crop_y0 = int(full_height * self.crop.y)
            crop_x1 = crop_x0 + int(full_width * zoom)
            crop_y1 = crop_y0 + int(full_height * zoom)

            # 2) Crop to the ROI.
            # 3) Resize to the target dimensions (still in the original dtype, e.g. uint16).
            raw_frame = raw_frame[crop_y0:crop_y1, crop_x0:crop_x1]

        preview_img = cv2.resize(raw_frame, (preview_width, preview_height), interpolation=cv2.INTER_AREA)
        resize_time = time.perf_counter() - resize_start

        # Compute histogram on raw resized data BEFORE any scaling (only for full frames)
        # This shows the actual data distribution for proper level adjustment
        hist_data = None
        if not adjust:
            # Compute histogram with reasonable bin count for performance
            # Use 1024 bins for good detail without overwhelming the frontend
            max_val = np.iinfo(raw_frame.dtype).max
            num_bins = 1024
            histogram, _ = np.histogram(preview_img, bins=num_bins, range=(0, max_val))
            hist_data = histogram.tolist()

        # 4) Convert to float32 and normalize to 0-1 range based on dtype.
        max_val = np.iinfo(raw_frame.dtype).max  # 255 for uint8, 65535 for uint16
        preview_float = preview_img.astype(np.float32) / max_val

        # 5) Apply levels adjustment if needed (values are now in 0-1 range).
        levels = self.levels
        if levels.needs_adjustment:
            preview_float = np.clip(preview_float, levels.min, levels.max)
            denom = (levels.max - levels.min) + 1e-8
            preview_float = (preview_float - levels.min) / denom

        # 6) Scale to [0..255] and convert to uint8.
        preview_float *= 255.0
        preview_uint8 = preview_float.astype(np.uint8)

        # 7) Apply colormap LUT if set (grayscale → RGB).
        if self._lut is not None:
            preview_out = cv2.cvtColor(self._lut[preview_uint8], cv2.COLOR_RGB2BGR)
        else:
            preview_out = preview_uint8

        # Use actual crop values based on whether adjustment was applied
        actual_crop = self.crop if adjust else PreviewCrop(x=0.0, y=0.0, k=0.0)

        metadata = PreviewFrameInfo(
            frame_idx=frame_idx,
            preview_width=preview_width,
            preview_height=preview_height,
            full_width=full_width,
            full_height=full_height,
            levels=levels,
            fmt=self._fmt,
            crop=actual_crop,
            histogram=hist_data,
            colormap=self._colormap,
        )

        # 8) Encode and return the final preview.
        encode_start = time.perf_counter()
        preview_frame = PreviewFrame.from_array(frame_array=preview_out, info=metadata)
        encode_time = time.perf_counter() - encode_start

        gen_time = time.perf_counter() - gen_start

        # Log timing at DEBUG level for performance diagnostics
        if frame_idx < 5 or frame_idx % 100 == 0:
            self.log.debug(
                f"Frame {frame_idx} preview generation: resize={resize_time * 1000:.1f}ms, "
                f"encode={encode_time * 1000:.1f}ms, total={gen_time * 1000:.1f}ms",
            )

        return preview_frame


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
    """Return the raw bytes of the NumPy array without any compression or encoding.
    Useful if you want to preserve the full bit depth (e.g. uint16).
    """
    return frame.tobytes()


def compress_uint16_frame_zlib(frame: np.ndarray) -> bytes:
    """Compress a 2D (or 3D) NumPy array of dtype=uint16 with zlib.
    Returns the compressed bytes.
    """
    # Ensure the array is C-contiguous, just in case
    if not frame.flags["C_CONTIGUOUS"]:
        frame = np.ascontiguousarray(frame)

    # Convert to raw bytes
    raw_bytes = frame.tobytes()

    # Compress with zlib (level=9 = max compression, can adjust for speed)
    return zlib.compress(raw_bytes, level=9)
