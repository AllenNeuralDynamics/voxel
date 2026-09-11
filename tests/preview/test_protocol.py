"""Golden and validation tests for the raw preview wire protocol."""

from copy import deepcopy

import msgpack
import numpy as np
import pytest

from vxl.preview.protocol import (
    DELIVERY_MAGIC,
    DELIVERY_PREFIX,
    SOURCE_FRAMING_VERSION,
    SOURCE_MAGIC,
    SOURCE_PREFIX,
    VOXEL_PREVIEW_FRAMING_VERSION,
    PreviewFrame,
    PreviewLayer,
    PreviewSourceHeader,
    PreviewViewport,
    SourceRectPx,
    StreamCursor,
    ValidBits,
    VoxelPreviewPacket,
    byte_shuffle_u16,
    byte_unshuffle_u16,
)


def _source_frame(frame: np.ndarray, *, valid_bits: ValidBits = 16) -> PreviewFrame:
    return PreviewFrame.from_source(
        frame,
        camera_id="camera-1",
        source_stream_id="stream-1",
        layer=PreviewLayer.OVERVIEW,
        frame_idx=7,
        viewport=PreviewViewport(),
        target_width=frame.shape[1],
        valid_bits=valid_bits,
    )


def test_byte_shuffle_golden_plane_order_and_byte_order() -> None:
    frame = np.array([[0x0001, 0x0203, 0xFF10]], dtype=np.uint16)
    shuffled = byte_shuffle_u16(frame, valid_bits=16)
    assert shuffled == bytes([0x01, 0x03, 0x10, 0x00, 0x02, 0xFF])
    assert np.array_equal(byte_unshuffle_u16(shuffled, width=3, height=1), frame)


@pytest.mark.parametrize(
    ("valid_bits", "dtype"), [(8, np.uint8), (10, np.uint16), (12, np.uint16), (14, np.uint16), (16, np.uint16)]
)
def test_round_trip_pixel_formats(
    valid_bits: ValidBits,
    dtype: type[np.uint8] | type[np.uint16],
) -> None:
    maximum = (1 << valid_bits) - 1
    values = np.array([0, 1, min(maximum, 0xFF), min(maximum, 0x100), maximum], dtype=dtype)
    frame = np.resize(values, (3, 5))

    source = _source_frame(frame, valid_bits=valid_bits)
    parsed = PreviewFrame.from_packed(source.pack())
    decoded = parsed.decode()

    assert decoded.dtype == np.uint16
    assert np.array_equal(decoded, frame.astype(np.uint16))
    assert parsed.header.valid_bits == valid_bits
    assert parsed.header.uncompressed_byte_length == frame.size * 2


def test_noncontiguous_and_big_endian_inputs_are_canonicalized() -> None:
    native = np.arange(99, dtype=np.uint16).reshape(9, 11)[:, ::2]
    big_endian = native.astype(">u2")

    assert not native.flags.c_contiguous
    assert np.array_equal(_source_frame(native).decode(), native)
    assert np.array_equal(_source_frame(big_endian).decode(), native)


def test_packet_header_contains_only_source_owned_metadata() -> None:
    source = _source_frame(np.arange(12, dtype=np.uint16).reshape(3, 4))
    packed = source.pack()
    magic, version, header_length = SOURCE_PREFIX.unpack_from(packed)
    header = msgpack.unpackb(packed[SOURCE_PREFIX.size : SOURCE_PREFIX.size + header_length], raw=False)

    assert magic == SOURCE_MAGIC
    assert version == SOURCE_FRAMING_VERSION
    assert header["camera_id"] == "camera-1"
    assert header["source_rect_px"] == {"x": 0, "y": 0, "width": 4, "height": 3}
    assert "channel_id" not in header
    assert "histogram" not in header
    assert "levels" not in header
    assert "bit_packing" not in header


def test_delivery_packet_wraps_frame_without_modifying_it() -> None:
    frame = _source_frame(np.arange(12, dtype=np.uint16).reshape(3, 4)).pack()
    delivery = VoxelPreviewPacket.wrap(
        frame,
        channel_id="channel-1",
        seq=9,
        state_cursor=StreamCursor(stream_id="state-1", seq=17),
        stamped_at_unix_us=1_234_567,
    )

    packed = delivery.pack()
    magic, version, _header_length = DELIVERY_PREFIX.unpack_from(packed)
    parsed = VoxelPreviewPacket.from_packed(packed)

    assert (magic, version) == (DELIVERY_MAGIC, VOXEL_PREVIEW_FRAMING_VERSION)
    assert parsed.header.channel_id == "channel-1"
    assert parsed.header.seq == 9
    assert parsed.header.state_cursor == StreamCursor(stream_id="state-1", seq=17)
    assert parsed.header.stamped_at_unix_us == 1_234_567
    assert parsed.frame == frame
    assert PreviewFrame.from_packed(parsed.frame).header.camera_id == "camera-1"


@pytest.mark.parametrize(
    ("frame", "valid_bits", "error"),
    [
        (np.zeros((2, 2, 1), dtype=np.uint16), 16, ValueError),
        (np.zeros((2, 2), dtype=np.int16), 16, TypeError),
        (np.full((2, 2), 1024, dtype=np.uint16), 10, ValueError),
    ],
)
def test_invalid_samples_are_rejected(frame: np.ndarray, valid_bits: ValidBits, error: type[Exception]) -> None:
    with pytest.raises(error):
        _source_frame(frame, valid_bits=valid_bits)


def test_invalid_framing_and_payload_are_rejected() -> None:
    packed = _source_frame(np.arange(12, dtype=np.uint16).reshape(3, 4)).pack()

    with pytest.raises(ValueError, match="prefix"):
        PreviewFrame.from_packed(packed[:4])
    with pytest.raises(ValueError, match="magic"):
        PreviewFrame.from_packed(b"NOPE" + packed[4:])
    with pytest.raises(ValueError, match="framing version"):
        PreviewFrame.from_packed(packed[:4] + bytes([99]) + packed[5:])
    with pytest.raises(ValueError, match="payload"):
        PreviewFrame.from_packed(packed[: -len(PreviewFrame.from_packed(packed).payload)])

    parsed = PreviewFrame.from_packed(packed)
    corrupt = PreviewFrame(
        header=deepcopy(parsed.header),
        payload=parsed.payload[:-1] + bytes([parsed.payload[-1] ^ 1]),
    )
    with pytest.raises(ValueError, match="Zstandard"):
        corrupt.decode()


def test_source_rect_must_fit_sensor() -> None:
    with pytest.raises(ValueError, match="extends beyond"):
        PreviewSourceHeader(
            camera_id="camera-1",
            source_stream_id="stream-1",
            layer=PreviewLayer.VIEWPORT,
            frame_idx=0,
            width=4,
            height=3,
            sensor_width=10,
            sensor_height=10,
            source_rect_px=SourceRectPx(x=8, y=8, width=4, height=3),
            valid_bits=16,
            uncompressed_byte_length=24,
        )
