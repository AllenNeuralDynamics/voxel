import numpy as np

from vxl.instrument import Instrument
from vxl.preview import PreviewFrame, PreviewLayer, PreviewViewport


async def test_preview_rejects_stale_source_generation(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    source_frames: list[tuple[str, PreviewLayer, bytes]] = []
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
        assert source_frames[-1] == ("gfp", PreviewLayer.OVERVIEW, source_packet)

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
        assert source_frames[-1] == ("rfp", PreviewLayer.OVERVIEW, source_packet)
    finally:
        unsub()
