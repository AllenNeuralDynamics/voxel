"""Tests for viewport-first preview rendering (``vxl.camera.preview``).

Covers the single-image ``preview_view`` path: overscan expansion, the "skip at a full
viewport" guard, and the server-authoritative ``rect`` surviving the wire envelope.
"""

import numpy as np

from vxl.camera.preview import RENDER_CAP, PreviewFrame, PreviewGenerator, PreviewViewport


def _frame(w: int = 2000, h: int = 1600) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 65535, size=(h, w), dtype=np.uint16)


def _gen(**kwargs) -> PreviewGenerator:
    return PreviewGenerator(frame_sink=lambda _f: None, **kwargs)


def test_expanded_grows_and_clamps() -> None:
    ex = PreviewViewport(x=0.4, y=0.4, w=0.2, h=0.2).expanded(0.25)
    assert ex.w > 0.2
    assert ex.h > 0.2
    assert ex.w <= 1.0
    assert ex.h <= 1.0
    assert ex.x >= 0.0
    assert ex.x + ex.w <= 1.0 + 1e-9
    assert PreviewViewport().expanded(0.25).w == 1.0  # a full viewport stays full


async def test_view_emitted_when_zoomed() -> None:
    captured: list[bytes] = []

    async def sink(packed: bytes) -> None:
        captured.append(packed)

    gen = _gen(view_sink=sink)
    try:
        await gen._generate_and_send_view(_frame(), 1, PreviewViewport(x=0.25, y=0.25, w=0.5, h=0.5))
    finally:
        gen.shutdown()

    assert len(captured) == 1
    view = PreviewFrame.from_packed(captured[0])  # survives the msgpack wire envelope
    assert view.info.rect.needs_adjustment
    assert view.info.rect.w > 0.5  # overscan-expanded, server-authoritative
    assert view.info.width <= RENDER_CAP
    assert view.info.histogram is None  # histogram rides the overview, not the view


async def test_no_view_at_full_viewport() -> None:
    captured: list[bytes] = []

    async def sink(packed: bytes) -> None:
        captured.append(packed)

    gen = _gen(view_sink=sink)
    try:
        await gen._generate_and_send_view(_frame(), 1, PreviewViewport())  # full sensor → overview covers it
    finally:
        gen.shutdown()

    assert captured == []
