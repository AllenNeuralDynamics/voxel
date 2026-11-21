"""The delivery packet (VXLP) and the latest-only frame queue of the legacy apps."""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from struct import Struct
from typing import Literal, Self, cast

import msgpack
from pydantic import Field
from vxlib.schema import FrozenModel
from vxlib.vector import StagePosition

from vxl.live import LiveLayer

DELIVERY_MAGIC = b"VXLP"
VOXEL_LIVE_FRAMING_VERSION = 1
VOXEL_LIVE_SCHEMA_VERSION = 1
DELIVERY_PREFIX = Struct(">4sBI")
MAX_DELIVERY_HEADER_BYTES = 64 * 1024

type LiveKey = tuple[str, LiveLayer]
type LiveEmission = tuple[str, LiveLayer, bytes]


class StreamCursor(FrozenModel):
    """Position in one identified ordered stream."""

    stream_id: str = Field(min_length=1)
    seq: int = Field(ge=0)


class VoxelLiveHeader(FrozenModel):
    """Voxel delivery ordering and authoritative application-state association."""

    delivery_schema_version: Literal[1] = VOXEL_LIVE_SCHEMA_VERSION
    channel_id: str = Field(min_length=1)
    seq: int = Field(ge=0)
    state_cursor: StreamCursor
    stamped_at_unix_us: int = Field(ge=0)
    frame_byte_length: int = Field(gt=0)
    position_um: StagePosition | None = None


@dataclass(frozen=True)
class VoxelLivePacket:
    """Voxel delivery header plus an opaque packed VXSF frame."""

    header: VoxelLiveHeader
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
        position_um: StagePosition | None = None,
    ) -> Self:
        """Wrap an already-packed VXSF frame without parsing or copying its payload twice."""
        packed_frame = bytes(frame)
        return cls(
            header=VoxelLiveHeader(
                channel_id=channel_id,
                seq=seq,
                state_cursor=state_cursor,
                stamped_at_unix_us=stamped_at_unix_us,
                frame_byte_length=len(packed_frame),
                position_um=position_um,
            ),
            frame=packed_frame,
        )

    @classmethod
    def from_packed(cls, packed: bytes | bytearray | memoryview) -> Self:
        """Parse Voxel delivery framing while leaving the VXSF frame opaque."""
        packet = memoryview(packed)
        if len(packet) < DELIVERY_PREFIX.size:
            raise ValueError("Voxel preview packet is truncated before its prefix")
        magic, framing_version, header_length = DELIVERY_PREFIX.unpack_from(packet)
        if magic != DELIVERY_MAGIC:
            raise ValueError("invalid Voxel preview magic")
        if framing_version != VOXEL_LIVE_FRAMING_VERSION:
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
            header=VoxelLiveHeader.model_validate(unpacked),
            frame=bytes(packet[frame_offset:]),
        )

    def pack(self) -> bytes:
        """Serialize the Voxel delivery header and unchanged VXSF frame."""
        header = cast("bytes", msgpack.packb(self.header.model_dump(mode="json"), use_bin_type=True))
        if not 0 < len(header) <= MAX_DELIVERY_HEADER_BYTES:
            raise ValueError(f"Voxel preview header is too large: {len(header)} bytes")
        return DELIVERY_PREFIX.pack(DELIVERY_MAGIC, VOXEL_LIVE_FRAMING_VERSION, len(header)) + header + self.frame


class LatestFrameQueue:
    """Async queue retaining at most one pending frame per preview key.

    Replacing a pending frame does not change its position, which prevents a
    busy stream from starving other keys already waiting to be handled.
    Producers never wait; consumers await :meth:`get`.
    """

    def __init__(self) -> None:
        self._items: OrderedDict[LiveKey, bytes] = OrderedDict()
        self._ready = asyncio.Event()

    def put(self, key: LiveKey, frame: bytes) -> None:
        """Insert or replace the pending frame for ``key`` without waiting."""
        self._items[key] = frame
        self._ready.set()

    async def get(self) -> tuple[LiveKey, bytes]:
        """Wait for and remove the oldest pending key and its latest frame."""
        while not self._items:
            self._ready.clear()
            await self._ready.wait()
        return self._items.popitem(last=False)

    def clear(self) -> None:
        """Discard every pending frame."""
        self._items.clear()
        self._ready.clear()

    def __len__(self) -> int:
        return len(self._items)


__all__ = [
    "DELIVERY_MAGIC",
    "DELIVERY_PREFIX",
    "VOXEL_LIVE_FRAMING_VERSION",
    "LatestFrameQueue",
    "LiveEmission",
    "LiveKey",
    "StreamCursor",
    "VoxelLiveHeader",
    "VoxelLivePacket",
]
