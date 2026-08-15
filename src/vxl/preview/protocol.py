from dataclasses import dataclass
from enum import StrEnum
from math import ceil
from struct import Struct
from typing import Literal, Self, cast

import cv2
import msgpack
import numpy as np
from numcodecs import Zstd
from pydantic import Field, field_validator, model_validator
from vxlib.schema import FrozenModel, SparseModel

SOURCE_MAGIC = b"VXPS"
SOURCE_FRAMING_VERSION = 1
SOURCE_SCHEMA_VERSION = 1
SOURCE_ENCODING = "u16-zstd-byte-shuffle-v1"
SOURCE_PREFIX = Struct(">4sBI")
MAX_SOURCE_HEADER_BYTES = 64 * 1024

DELIVERY_MAGIC = b"VXPD"
VOXEL_PREVIEW_FRAMING_VERSION = 1
VOXEL_PREVIEW_SCHEMA_VERSION = 1
DELIVERY_PREFIX = Struct(">4sBI")
MAX_DELIVERY_HEADER_BYTES = 64 * 1024

# Level 1 is the measured low-latency point for real preview frames. The frame checksum lets
# consumers reject corruption before uploading pixels; it is part of the v1 encoding contract.
_ZSTD = Zstd(level=1, checksum=True)

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


class PreviewViewport(FrozenModel):
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


type PreviewKey = tuple[str, PreviewLayer]
type PreviewSourceEmission = tuple[str, PreviewLayer, bytes]
type PreviewEmission = tuple[str, PreviewLayer, bytes]


class SourceRectPx(FrozenModel):
    """Source region represented by an image, in integer sensor pixels."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PreviewSourceHeader(SparseModel):
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


def _parse_preview_source(
    packed: bytes | bytearray | memoryview,
) -> tuple[memoryview, PreviewSourceHeader, int]:
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
    return packet, PreviewSourceHeader.model_validate(unpacked), payload_offset


def preview_source_header(packed: bytes | bytearray | memoryview) -> PreviewSourceHeader:
    """Parse and validate only the VXPS header without copying its compressed payload."""
    return _parse_preview_source(packed)[1]


class StreamCursor(FrozenModel):
    """Position in one identified ordered stream."""

    stream_id: str = Field(min_length=1)
    seq: int = Field(ge=0)


class VoxelPreviewHeader(FrozenModel):
    """Voxel delivery ordering and authoritative application-state association."""

    delivery_schema_version: Literal[1] = VOXEL_PREVIEW_SCHEMA_VERSION
    channel_id: str = Field(min_length=1)
    seq: int = Field(ge=0)
    state_cursor: StreamCursor
    stamped_at_unix_us: int = Field(ge=0)
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
        packet, header, payload_offset = _parse_preview_source(packed)
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
class VoxelPreviewPacket:
    """Voxel delivery header plus an opaque packed VXPS frame."""

    header: VoxelPreviewHeader
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
        seq: int,
        state_cursor: StreamCursor,
        stamped_at_unix_us: int,
    ) -> Self:
        """Wrap an already-packed VXPS frame without parsing or copying its payload twice."""
        packed_frame = bytes(frame)
        return cls(
            header=VoxelPreviewHeader(
                channel_id=channel_id,
                seq=seq,
                state_cursor=state_cursor,
                stamped_at_unix_us=stamped_at_unix_us,
                frame_byte_length=len(packed_frame),
            ),
            frame=packed_frame,
        )

    @classmethod
    def from_packed(cls, packed: bytes | bytearray | memoryview) -> Self:
        """Parse Voxel delivery framing while leaving the VXPS frame opaque."""
        packet = memoryview(packed)
        if len(packet) < DELIVERY_PREFIX.size:
            raise ValueError("Voxel preview packet is truncated before its prefix")
        magic, framing_version, header_length = DELIVERY_PREFIX.unpack_from(packet)
        if magic != DELIVERY_MAGIC:
            raise ValueError("invalid Voxel preview magic")
        if framing_version != VOXEL_PREVIEW_FRAMING_VERSION:
            raise ValueError(f"unsupported Voxel preview framing version: {framing_version}")
        if not 0 < header_length <= MAX_DELIVERY_HEADER_BYTES:
            raise ValueError(f"invalid station preview header length: {header_length}")

        frame_offset = DELIVERY_PREFIX.size + header_length
        if len(packet) <= frame_offset:
            raise ValueError("Voxel preview packet is truncated before its frame")
        try:
            unpacked = msgpack.unpackb(packet[DELIVERY_PREFIX.size : frame_offset], raw=False)
        except (msgpack.ExtraData, msgpack.FormatError, msgpack.StackError, ValueError) as exc:
            raise ValueError("invalid Voxel preview MessagePack header") from exc
        if not isinstance(unpacked, dict):
            raise ValueError("Voxel preview header must be a MessagePack map")
        return cls(
            header=VoxelPreviewHeader.model_validate(unpacked),
            frame=bytes(packet[frame_offset:]),
        )

    def pack(self) -> bytes:
        """Serialize the Voxel delivery header and unchanged VXPS frame."""
        header = cast("bytes", msgpack.packb(self.header.model_dump(mode="json"), use_bin_type=True))
        if not 0 < len(header) <= MAX_DELIVERY_HEADER_BYTES:
            raise ValueError(f"Voxel preview header is too large: {len(header)} bytes")
        return DELIVERY_PREFIX.pack(DELIVERY_MAGIC, VOXEL_PREVIEW_FRAMING_VERSION, len(header)) + header + self.frame
