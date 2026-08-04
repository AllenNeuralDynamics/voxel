import asyncio
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import partial
from math import ceil
from struct import Struct
from typing import Literal, Self, cast
from uuid import uuid4

import cv2
import msgpack
import numpy as np
from numcodecs import Zstd
from pydantic import Field, field_validator, model_validator

from vxlib import SchemaModel

SOURCE_MAGIC = b"VXPS"
SOURCE_FRAMING_VERSION = 1
SOURCE_SCHEMA_VERSION = 1
SOURCE_ENCODING = "u16-zstd-byte-shuffle-v1"
SOURCE_PREFIX = Struct(">4sBI")
MAX_SOURCE_HEADER_BYTES = 64 * 1024

DELIVERY_MAGIC = b"VXPD"
DELIVERY_FRAMING_VERSION = 1
DELIVERY_SCHEMA_VERSION = 1
DELIVERY_PREFIX = Struct(">4sBI")
MAX_DELIVERY_HEADER_BYTES = 64 * 1024

# Level 1 is the measured low-latency point for real preview frames. The frame checksum lets
# consumers reject corruption before uploading pixels; it is part of the v1 encoding contract.
_ZSTD = Zstd(level=1, checksum=True)


OVERVIEW_WIDTH = 2048  # overview output width (the overview is the main view)
RENDER_CAP = 2048  # max width of a single coherent viewport-image render (rendered on demand, not per frame)
# Fraction each axis grows beyond the viewport so small pans stay covered without a re-render. Its area cost
# is quadratic in 1 + 2*margin, so keep it small while retaining a little coverage during interaction.
OVERSCAN_MARGIN = 0.05


type ValidBits = Literal[8, 10, 12, 14, 16]


def byte_shuffle_u16(frame: np.ndarray, *, valid_bits: ValidBits) -> bytes:
    """Return canonical low-byte-plane/high-byte-plane bytes for a 2-D image."""
    if frame.ndim != 2:
        raise ValueError(f"preview frame must be 2-D, got shape {frame.shape}")
    if frame.dtype.kind != "u" or frame.dtype.itemsize not in {1, 2}:
        raise TypeError(f"preview frame must contain uint8 or uint16 samples, got {frame.dtype}")
    if valid_bits not in {8, 10, 12, 14, 16}:
        raise ValueError(f"unsupported valid_bits: {valid_bits}")
    if frame.dtype.itemsize == 1 and valid_bits != 8:
        raise ValueError("uint8 input requires valid_bits=8")
    if frame.size and int(frame.max()) >= 1 << valid_bits:
        raise ValueError(f"preview frame contains samples outside {valid_bits}-bit range")

    canonical = np.ascontiguousarray(frame, dtype="<u2")
    interleaved = canonical.view(np.uint8).reshape(-1, 2)
    shuffled = np.empty(canonical.size * 2, dtype=np.uint8)
    shuffled[: canonical.size] = interleaved[:, 0]
    shuffled[canonical.size :] = interleaved[:, 1]
    return shuffled.tobytes()


def byte_unshuffle_u16(shuffled: bytes | bytearray | memoryview, *, width: int, height: int) -> np.ndarray:
    """Reconstruct a native-endian uint16 image from canonical shuffled bytes."""
    pixel_count = width * height
    expected_length = pixel_count * 2
    if len(shuffled) != expected_length:
        raise ValueError(f"decoded payload is {len(shuffled)} bytes; expected {expected_length}")

    planes = np.frombuffer(shuffled, dtype=np.uint8)
    interleaved = np.empty((pixel_count, 2), dtype=np.uint8)
    interleaved[:, 0] = planes[:pixel_count]
    interleaved[:, 1] = planes[pixel_count:]
    return interleaved.view("<u2").reshape(height, width).astype(np.uint16, copy=False)


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


class PreviewLayer(StrEnum):
    """Independently replaceable image layers derived from one camera capture."""

    OVERVIEW = "overview"
    VIEWPORT = "viewport"


class SourceRectPx(SchemaModel):
    """Source region represented by an image, in integer sensor pixels."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PreviewSourceHeader(SchemaModel):
    """Immutable source metadata supplied by a camera node."""

    source_schema_version: Literal[1] = SOURCE_SCHEMA_VERSION
    camera_id: str = Field(min_length=1)
    source_stream_id: str = Field(min_length=1)
    layer: PreviewLayer
    frame_idx: int = Field(ge=0)
    captured_at_unix_us: int | None = Field(default=None, ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    sensor_width: int = Field(gt=0)
    sensor_height: int = Field(gt=0)
    source_rect_px: SourceRectPx
    valid_bits: ValidBits
    encoding: Literal["u16-zstd-byte-shuffle-v1"] = SOURCE_ENCODING
    uncompressed_byte_length: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_geometry(self) -> Self:
        rect = self.source_rect_px
        if rect.x + rect.width > self.sensor_width or rect.y + rect.height > self.sensor_height:
            raise ValueError("source_rect_px extends beyond the sensor")
        expected_length = self.width * self.height * np.dtype(np.uint16).itemsize
        if self.uncompressed_byte_length != expected_length:
            raise ValueError(
                f"uncompressed_byte_length must be {expected_length} for a {self.width}x{self.height} uint16 image"
            )
        return self


class PreviewDeliveryHeader(SchemaModel):
    """Routing and sequencing metadata supplied by the control computer."""

    delivery_schema_version: Literal[1] = DELIVERY_SCHEMA_VERSION
    channel_id: str = Field(min_length=1)
    delivery_stream_id: str = Field(min_length=1)
    delivery_seq: int = Field(ge=0)
    frame_byte_length: int = Field(gt=0)


@dataclass(frozen=True)
class PreviewFrame:
    """Camera-owned source header plus an opaque shuffled Zstandard payload."""

    header: PreviewSourceHeader
    payload: bytes

    @classmethod
    def from_source(
        cls,
        source: np.ndarray,
        *,
        camera_id: str,
        source_stream_id: str,
        layer: PreviewLayer,
        frame_idx: int,
        viewport: PreviewViewport,
        target_width: int,
        valid_bits: ValidBits,
        captured_at_unix_us: int | None = None,
    ) -> Self:
        """Crop, resize, shuffle, and compress a sensor frame into one decodable source frame."""
        if source.ndim != 2:
            raise ValueError(f"preview source must be 2-D, got shape {source.shape}")
        if not source.size:
            raise ValueError("preview source must not be empty")
        if target_width <= 0:
            raise ValueError(f"target_width must be positive, got {target_width}")

        sensor_height, sensor_width = source.shape
        x0 = max(0, min(int(viewport.x * sensor_width), sensor_width - 1))
        y0 = max(0, min(int(viewport.y * sensor_height), sensor_height - 1))
        x1 = max(x0 + 1, min(ceil((viewport.x + viewport.w) * sensor_width), sensor_width))
        y1 = max(y0 + 1, min(ceil((viewport.y + viewport.h) * sensor_height), sensor_height))
        source_rect_px = SourceRectPx(x=x0, y=y0, width=x1 - x0, height=y1 - y0)

        crop = source[y0:y1, x0:x1]
        width = min(source_rect_px.width, target_width)
        height = max(1, round(source_rect_px.height * width / source_rect_px.width))
        if crop.shape != (height, width):
            frame = cv2.resize(crop, (width, height), interpolation=cv2.INTER_NEAREST_EXACT)
        else:
            frame = crop

        shuffled = byte_shuffle_u16(frame, valid_bits=valid_bits)
        header = PreviewSourceHeader(
            camera_id=camera_id,
            source_stream_id=source_stream_id,
            layer=layer,
            frame_idx=frame_idx,
            captured_at_unix_us=captured_at_unix_us,
            width=width,
            height=height,
            sensor_width=sensor_width,
            sensor_height=sensor_height,
            source_rect_px=source_rect_px,
            valid_bits=valid_bits,
            uncompressed_byte_length=len(shuffled),
        )
        return cls(header=header, payload=bytes(_ZSTD.encode(shuffled)))

    @classmethod
    def from_packed(cls, packed: bytes | bytearray | memoryview) -> Self:
        """Parse and validate framing and source metadata without decoding pixels."""
        packet = memoryview(packed)
        if len(packet) < SOURCE_PREFIX.size:
            raise ValueError("preview source packet is truncated before its prefix")
        magic, framing_version, header_length = SOURCE_PREFIX.unpack_from(packet)
        if magic != SOURCE_MAGIC:
            raise ValueError("invalid preview source magic")
        if framing_version != SOURCE_FRAMING_VERSION:
            raise ValueError(f"unsupported preview source framing version: {framing_version}")
        if not 0 < header_length <= MAX_SOURCE_HEADER_BYTES:
            raise ValueError(f"invalid preview source header length: {header_length}")

        payload_offset = SOURCE_PREFIX.size + header_length
        if len(packet) <= payload_offset:
            raise ValueError("preview source packet is truncated before its payload")
        try:
            unpacked = msgpack.unpackb(packet[SOURCE_PREFIX.size : payload_offset], raw=False)
        except (msgpack.ExtraData, msgpack.FormatError, msgpack.StackError, ValueError) as exc:
            raise ValueError("invalid preview source MessagePack header") from exc
        if not isinstance(unpacked, dict):
            raise ValueError("preview source header must be a MessagePack map")
        header = PreviewSourceHeader.model_validate(unpacked)
        return cls(header=header, payload=bytes(packet[payload_offset:]))

    def pack(self) -> bytes:
        """Serialize prefix, MessagePack source header, and compressed payload."""
        header = cast("bytes", msgpack.packb(self.header.model_dump(mode="json"), use_bin_type=True))
        if not 0 < len(header) <= MAX_SOURCE_HEADER_BYTES:
            raise ValueError(f"preview source header is too large: {len(header)} bytes")
        return SOURCE_PREFIX.pack(SOURCE_MAGIC, SOURCE_FRAMING_VERSION, len(header)) + header + self.payload

    def decode(self) -> np.ndarray:
        """Decompress and unshuffle the source payload into a uint16 image."""
        try:
            shuffled = _ZSTD.decode(self.payload)
        except Exception as exc:
            raise ValueError("invalid Zstandard preview payload") from exc
        if len(shuffled) != self.header.uncompressed_byte_length:
            raise ValueError(
                f"decoded payload is {len(shuffled)} bytes; expected {self.header.uncompressed_byte_length}"
            )
        return byte_unshuffle_u16(shuffled, width=self.header.width, height=self.header.height)


@dataclass(frozen=True)
class PreviewFramePacket:
    """Control-owned delivery header plus an opaque packed preview frame."""

    header: PreviewDeliveryHeader
    frame: bytes

    def __post_init__(self) -> None:
        if len(self.frame) != self.header.frame_byte_length:
            raise ValueError(f"frame is {len(self.frame)} bytes; expected {self.header.frame_byte_length}")

    @classmethod
    def wrap(
        cls,
        frame: bytes | bytearray | memoryview,
        *,
        channel_id: str,
        delivery_stream_id: str,
        delivery_seq: int,
    ) -> Self:
        """Wrap an already-packed preview frame without parsing its contents."""
        packed_frame = bytes(frame)
        return cls(
            header=PreviewDeliveryHeader(
                channel_id=channel_id,
                delivery_stream_id=delivery_stream_id,
                delivery_seq=delivery_seq,
                frame_byte_length=len(packed_frame),
            ),
            frame=packed_frame,
        )

    @classmethod
    def from_packed(cls, packed: bytes | bytearray | memoryview) -> Self:
        """Parse and validate delivery framing while leaving the preview frame opaque."""
        packet = memoryview(packed)
        if len(packet) < DELIVERY_PREFIX.size:
            raise ValueError("preview delivery packet is truncated before its prefix")
        magic, framing_version, header_length = DELIVERY_PREFIX.unpack_from(packet)
        if magic != DELIVERY_MAGIC:
            raise ValueError("invalid preview delivery magic")
        if framing_version != DELIVERY_FRAMING_VERSION:
            raise ValueError(f"unsupported preview delivery framing version: {framing_version}")
        if not 0 < header_length <= MAX_DELIVERY_HEADER_BYTES:
            raise ValueError(f"invalid preview delivery header length: {header_length}")

        frame_offset = DELIVERY_PREFIX.size + header_length
        if len(packet) <= frame_offset:
            raise ValueError("preview delivery packet is truncated before its frame")
        try:
            unpacked = msgpack.unpackb(packet[DELIVERY_PREFIX.size : frame_offset], raw=False)
        except (msgpack.ExtraData, msgpack.FormatError, msgpack.StackError, ValueError) as exc:
            raise ValueError("invalid preview delivery MessagePack header") from exc
        if not isinstance(unpacked, dict):
            raise ValueError("preview delivery header must be a MessagePack map")
        return cls(
            header=PreviewDeliveryHeader.model_validate(unpacked),
            frame=bytes(packet[frame_offset:]),
        )

    def pack(self) -> bytes:
        """Serialize the delivery prefix, header, and unchanged preview frame."""
        header = cast("bytes", msgpack.packb(self.header.model_dump(mode="json"), use_bin_type=True))
        if not 0 < len(header) <= MAX_DELIVERY_HEADER_BYTES:
            raise ValueError(f"preview delivery header is too large: {len(header)} bytes")
        return DELIVERY_PREFIX.pack(DELIVERY_MAGIC, DELIVERY_FRAMING_VERSION, len(header)) + header + self.frame


@dataclass(slots=True)
class PreviewHealth:
    frames: int = 0
    overviews_generated: int = 0
    overview_busy_drops: int = 0
    generation_ms_total: float = 0.0
    generation_ms_max: float = 0.0
    publish_sent: int = 0
    publish_busy_drops: int = 0

    @property
    def generation_ms_average(self) -> float:
        return self.generation_ms_total / self.overviews_generated if self.overviews_generated else 0.0

    def record_frame(self) -> None:
        self.frames += 1

    def record_overview(self, elapsed_ms: float) -> None:
        self.overviews_generated += 1
        self.generation_ms_total += elapsed_ms
        self.generation_ms_max = max(self.generation_ms_max, elapsed_ms)

    def record_overview_drop(self) -> None:
        self.overview_busy_drops += 1

    def record_publish(self) -> None:
        self.publish_sent += 1

    def record_publish_drop(self) -> None:
        self.publish_busy_drops += 1

    def snapshot(self) -> "PreviewHealth":
        snapshot = replace(self)
        self.frames = 0
        self.overviews_generated = 0
        self.overview_busy_drops = 0
        self.generation_ms_total = 0.0
        self.generation_ms_max = 0.0
        self.publish_sent = 0
        self.publish_busy_drops = 0
        return snapshot


type _OverviewFuture = asyncio.Future[PreviewFrame]
type _Sink = Callable[[PreviewFrame], None]


class PreviewGenerator:
    """Generates the overview frame and the zoomed viewport image from raw camera frames.

    The overview is always generated at `target_width`. The viewport image is one coherent crop
    (expanded by overscan) at the display resolution, replacing the old pyramid tiles.
    """

    def __init__(
        self,
        sink: _Sink,
        uid: str,
        *,
        viewport: PreviewViewport | None = None,
        target_width: int = OVERVIEW_WIDTH,
    ) -> None:
        self._camera_id = uid
        self._sink = sink
        self._target_width: int = target_width
        self._viewport = viewport or PreviewViewport()
        self._log = logging.getLogger(f"{self._camera_id}.PreviewGenerator")

        self._frame_idx: int = 0
        self._source_stream_id = uuid4().hex
        self._work_epoch = 0
        self._current_frame: np.ndarray | None = None
        self._current_valid_bits: ValidBits = 16

        self._viewport_task: asyncio.Task[None] | None = None
        self._overview_future: _OverviewFuture | None = None
        self._overview_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PreviewOverview")
        self._viewport_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PreviewViewport")

        self.health = PreviewHealth()

    def set_viewport(self, viewport: PreviewViewport, *, regenerate: bool = False) -> asyncio.Task[None] | None:
        self._viewport = viewport
        if regenerate and self._current_frame is not None:
            return self._schedule_viewport(
                self._current_frame,
                self._frame_idx,
                viewport,
                valid_bits=self._current_valid_bits,
                source_stream_id=self._source_stream_id,
            )
        return None

    def submit_frame(self, frame: np.ndarray, idx: int, *, valid_bits: ValidBits = 16) -> None:
        """Process a new raw frame: dispatch overview and viewport work in the background.

        The viewport uses cancel-stale (latest viewport invalidates prior work). Overview
        uses skip-if-busy — if the previous overview hasn't finished, drop this
        frame's preview rather than queueing. Returns immediately so callers
        (preview loop, acquisition grab loop) are not gated by preview work.
        """
        self._frame_idx = idx
        self._current_frame = frame
        self._current_valid_bits = valid_bits
        source_stream_id = self._source_stream_id

        self._schedule_viewport(
            frame,
            idx,
            self._viewport,
            valid_bits=valid_bits,
            source_stream_id=source_stream_id,
        )

        self.health.record_frame()
        if self._overview_future is None or self._overview_future.done():
            gen_start = time.perf_counter()
            work_epoch = self._work_epoch
            loop = asyncio.get_running_loop()
            self._overview_future = loop.run_in_executor(
                self._overview_executor,
                partial(
                    PreviewFrame.from_source,
                    frame,
                    camera_id=self._camera_id,
                    source_stream_id=source_stream_id,
                    layer=PreviewLayer.OVERVIEW,
                    frame_idx=idx,
                    viewport=PreviewViewport(),
                    target_width=self._target_width,
                    valid_bits=valid_bits,
                ),
            )
            self._overview_future.add_done_callback(
                partial(
                    self._on_overview_done,
                    frame_idx=idx,
                    gen_start=gen_start,
                    work_epoch=work_epoch,
                )
            )
        else:
            self.health.record_overview_drop()  # Gate 1 drop: prior overview still generating

    def reset_stream(self) -> None:
        """Start a new camera capture identity before resetting frame indices."""
        self.cancel_pending()
        self._current_frame = None
        self._source_stream_id = uuid4().hex

    def cancel_pending(self) -> None:
        """Cancel preview work without shutting down the reusable worker executors."""
        self._work_epoch += 1
        self._cancel_viewport_task()
        if self._overview_future is not None and not self._overview_future.done():
            self._overview_future.cancel()
        self._overview_future = None

    def close(self) -> None:
        """Shutdown the preview generator and cleanup resources."""
        self.cancel_pending()
        self._overview_executor.shutdown(wait=False, cancel_futures=True)
        self._viewport_executor.shutdown(wait=False, cancel_futures=True)

    def _cancel_viewport_task(self) -> None:
        """Cancel the current viewport render and discard its result."""
        if self._viewport_task is not None and not self._viewport_task.done():
            self._viewport_task.cancel()
        self._viewport_task = None

    def _schedule_viewport(
        self,
        frame: np.ndarray,
        frame_idx: int,
        viewport: PreviewViewport,
        *,
        valid_bits: ValidBits,
        source_stream_id: str,
    ) -> asyncio.Task[None]:
        work_epoch = self._work_epoch

        async def generate_and_send() -> None:
            if not viewport.needs_adjustment:
                return
            render_viewport = viewport.expanded(OVERSCAN_MARGIN)
            try:
                viewport_frame = await asyncio.get_running_loop().run_in_executor(
                    self._viewport_executor,
                    partial(
                        PreviewFrame.from_source,
                        frame,
                        camera_id=self._camera_id,
                        source_stream_id=source_stream_id,
                        layer=PreviewLayer.VIEWPORT,
                        frame_idx=frame_idx,
                        viewport=render_viewport,
                        target_width=RENDER_CAP,
                        valid_bits=valid_bits,
                    ),
                )
            except asyncio.CancelledError:
                return
            if work_epoch != self._work_epoch:
                return
            self._sink(viewport_frame)

        self._cancel_viewport_task()
        task = asyncio.create_task(generate_and_send())
        self._viewport_task = task
        return task

    def _on_overview_done(
        self,
        future: _OverviewFuture,
        *,
        frame_idx: int,
        gen_start: float,
        work_epoch: int,
    ) -> None:
        if future.cancelled() or work_epoch != self._work_epoch:
            return
        try:
            overview = future.result()
        except Exception:
            self._log.exception("Failed to generate overview frame %d", frame_idx)
            return
        gen_time = time.perf_counter() - gen_start
        self.health.record_overview(gen_time * 1000)
        if frame_idx < 5 or frame_idx % 100 == 0:
            self._log.debug(f"Overview frame {frame_idx}: {gen_time * 1000:.1f}ms")
        self._sink(overview)
