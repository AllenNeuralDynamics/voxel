"""Tests for the version 1 delivery packet and the frame queue of the legacy apps."""

import numpy as np
import pytest
from vxlib.vector import StagePosition

from vxl._legacy.live import (
    DELIVERY_MAGIC,
    DELIVERY_PREFIX,
    VOXEL_LIVE_FRAMING_VERSION,
    LatestFrameQueue,
    StreamCursor,
    VoxelLivePacket,
)
from vxl.live import LiveFrame, LiveLayer, LiveViewport


@pytest.mark.parametrize("position", [None, StagePosition(x=1, y=-2, z=3.5)])
def test_delivery_packet_wraps_frame_without_modifying_it(position: StagePosition | None) -> None:
    frame = LiveFrame.from_source(
        np.arange(12, dtype=np.uint16).reshape(3, 4),
        camera_id="camera-1",
        source_stream_id="stream-1",
        layer=LiveLayer.OVERVIEW,
        frame_idx=7,
        viewport=LiveViewport(),
        target_width=4,
        valid_bits=16,
    ).pack()
    delivery = VoxelLivePacket.wrap(
        frame,
        channel_id="channel-1",
        seq=9,
        state_cursor=StreamCursor(stream_id="state-1", seq=17),
        stamped_at_unix_us=1_234_567,
        position_um=position,
    )

    packed = delivery.pack()
    magic, version, _header_length = DELIVERY_PREFIX.unpack_from(packed)
    parsed = VoxelLivePacket.from_packed(packed)

    assert (magic, version) == (DELIVERY_MAGIC, VOXEL_LIVE_FRAMING_VERSION)
    assert parsed.header.channel_id == "channel-1"
    assert parsed.header.seq == 9
    assert parsed.header.state_cursor == StreamCursor(stream_id="state-1", seq=17)
    assert parsed.header.stamped_at_unix_us == 1_234_567
    assert parsed.header.position_um == position
    assert parsed.header.model_dump()["position_um"] == (position.model_dump() if position else None)
    assert parsed.frame == frame
    assert LiveFrame.from_packed(parsed.frame).header.camera_id == "camera-1"


async def test_latest_frame_queue_replaces_only_the_matching_pending_stream() -> None:
    queue = LatestFrameQueue()
    overview = ("488", LiveLayer.OVERVIEW)
    viewport = ("488", LiveLayer.VIEWPORT)

    queue.put(overview, b"sending")
    assert await queue.get() == (overview, b"sending")

    queue.put(overview, b"stale")
    queue.put(overview, b"latest")
    queue.put(viewport, b"viewport")

    assert await queue.get() == (overview, b"latest")
    assert await queue.get() == (viewport, b"viewport")
