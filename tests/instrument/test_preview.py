from types import SimpleNamespace

import numpy as np
import pytest

from vxl.instrument import AcquisitionMode, Instrument
from vxl.preview import PreviewFrame, PreviewLayer, PreviewSourceEmission, PreviewViewport
from vxl.preview.protocol import StagePosition


async def test_preview_rejects_stale_source_generation(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    source_frames: list[PreviewSourceEmission] = []
    unsub = instrument.preview.subscribe(source_frames.append)
    try:
        source_packet = PreviewFrame.from_source(
            np.zeros((8, 8), dtype=np.uint16),
            camera_id="camera_1",
            source_stream_id=instrument._preview_source_ids["camera_1"],
            layer=PreviewLayer.OVERVIEW,
            frame_idx=0,
            viewport=PreviewViewport(),
            target_width=8,
            valid_bits=16,
        ).pack()
        await instrument._emit_preview_frame("camera_1", PreviewLayer.OVERVIEW, source_packet)
        assert source_frames[-1] == ("gfp", PreviewLayer.OVERVIEW, source_packet, None)

        preview_revision = instrument.preview_revision.value
        await instrument.set_active_profile("single_rfp")
        assert instrument.preview_revision.value == preview_revision + 1
        await instrument._emit_preview_frame("camera_1", PreviewLayer.OVERVIEW, source_packet)
        assert len(source_frames) == 1
        source_packet = PreviewFrame.from_source(
            np.zeros((8, 8), dtype=np.uint16),
            camera_id="camera_1",
            source_stream_id=instrument._preview_source_ids["camera_1"],
            layer=PreviewLayer.OVERVIEW,
            frame_idx=0,
            viewport=PreviewViewport(),
            target_width=8,
            valid_bits=16,
        ).pack()
        await instrument._emit_preview_frame("camera_1", PreviewLayer.OVERVIEW, source_packet)
        assert source_frames[-1] == ("rfp", PreviewLayer.OVERVIEW, source_packet, None)
    finally:
        unsub()


async def test_preview_position_survives_stop_but_not_stream_reset(
    opened_instrument: Instrument, monkeypatch: pytest.MonkeyPatch
) -> None:
    instrument = opened_instrument
    stage = instrument._hal.stage
    samples = [SimpleNamespace(value=value) for value in (10.0, 20.0, 30.0)]
    for axis, sample in zip((stage.x, stage.y, stage.z), samples, strict=True):
        monkeypatch.setattr(axis, "position", sample)
    delivered: list[PreviewSourceEmission] = []
    unsub = instrument.preview.subscribe(delivered.append)

    async def emit(frame_idx: int, layer: PreviewLayer = PreviewLayer.VIEWPORT) -> None:
        packet = PreviewFrame.from_source(
            np.zeros((8, 8), dtype=np.uint16),
            camera_id="camera_1",
            source_stream_id=instrument._preview_source_ids["camera_1"],
            layer=layer,
            frame_idx=frame_idx,
            viewport=PreviewViewport(),
            target_width=8,
            valid_bits=16,
        ).pack()
        await instrument._emit_preview_frame("camera_1", layer, packet)

    try:
        await instrument._mode.set(AcquisitionMode.PREVIEW)
        instrument._preview_channels = list(instrument.active_channels.values())
        await emit(3, PreviewLayer.OVERVIEW)
        assert delivered[-1][3] == StagePosition(x=10, y=20, z=30)
        await instrument.stop_preview()
        samples[0].value = 99.0
        await emit(3)
        assert delivered[-1][3] == StagePosition(x=10, y=20, z=30)
        await emit(4)
        assert delivered[-1][3] is None  # An unseen cached frame must not acquire a post-stop position.

        await instrument._mode.set(AcquisitionMode.PREVIEW)
        for frame_idx in range(5, 22):
            await emit(frame_idx)
        assert len(instrument._preview_positions["camera_1"]) == 16
        await emit(3)
        assert delivered[-1][3] is None  # Evicted captures must not be re-anchored either.

        await instrument._reset_preview()
        assert not instrument._preview_positions
        await emit(3)
        assert delivered[-1][3] == StagePosition(x=99, y=20, z=30)
        samples[1].value = None
        await emit(4)
        assert delivered[-1][3] is None
        await instrument.close()
        assert not instrument._preview_positions
    finally:
        unsub()
