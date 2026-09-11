"""Tests for raw overview and viewport generation."""

import asyncio
from collections.abc import Callable

import numpy as np
from ome_zarr_writer import FrameLease

from vxl.preview import LatestFrameQueue, PreviewFrame, PreviewGenerator, PreviewLayer, PreviewViewport
from vxl.preview.generator import RENDER_CAP


def _frame(w: int = 2000, h: int = 1600) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 65535, size=(h, w), dtype=np.uint16)


def _discard(_frame: PreviewFrame) -> None:
    pass


def _gen(sink: Callable[[PreviewFrame], None] = _discard, **kwargs) -> PreviewGenerator:
    kwargs.setdefault("uid", "camera")
    return PreviewGenerator(sink=sink, **kwargs)


def test_expanded_grows_and_clamps() -> None:
    ex = PreviewViewport(x=0.4, y=0.4, w=0.2, h=0.2).expanded(0.25)
    assert ex.w > 0.2
    assert ex.h > 0.2
    assert ex.w <= 1.0
    assert ex.h <= 1.0
    assert ex.x >= 0.0
    assert ex.x + ex.w <= 1.0 + 1e-9
    assert PreviewViewport().expanded(0.25).w == 1.0  # a full viewport stays full


async def test_viewport_emitted_when_zoomed() -> None:
    captured: list[PreviewFrame] = []
    gen = _gen(sink=captured.append, viewport=PreviewViewport(x=0.25, y=0.25, w=0.5, h=0.5))
    try:
        gen.submit_frame(_frame(), 1)
        assert gen._viewport_task is not None
        await gen._viewport_task
    finally:
        gen.close()

    view = next(frame for frame in captured if frame.header.layer is PreviewLayer.VIEWPORT)
    assert view.header.layer is PreviewLayer.VIEWPORT
    assert view.header.source_rect_px.width > 1000  # includes overscan beyond the requested half-sensor viewport
    assert view.header.width <= RENDER_CAP
    assert view.decode().shape == (view.header.height, view.header.width)


async def test_no_viewport_frame_at_full_viewport() -> None:
    captured: list[PreviewFrame] = []
    gen = _gen(sink=captured.append)
    try:
        gen.submit_frame(_frame(), 1)
        assert gen._viewport_task is None
        assert gen._overview_future is not None
        await gen._overview_future
    finally:
        gen.close()

    assert all(frame.header.layer is not PreviewLayer.VIEWPORT for frame in captured)


async def test_latest_frame_queue_replaces_only_the_matching_pending_stream() -> None:
    queue = LatestFrameQueue()
    overview = ("488", PreviewLayer.OVERVIEW)
    viewport = ("488", PreviewLayer.VIEWPORT)

    queue.put(overview, b"sending")
    assert await queue.get() == (overview, b"sending")

    queue.put(overview, b"stale")
    queue.put(overview, b"latest")
    queue.put(viewport, b"viewport")

    assert await queue.get() == (overview, b"latest")
    assert await queue.get() == (viewport, b"viewport")


async def test_overview_and_viewport_share_capture_identity_and_resize_exactly() -> None:
    captured: list[PreviewFrame] = []
    released: list[bool] = []
    frame = _frame(w=230, h=180)
    gen = _gen(
        sink=captured.append,
        uid="camera-1",
        target_width=204,
        viewport=PreviewViewport(x=0.25, y=0.25, w=0.5, h=0.5),
    )
    try:
        gen.submit_frame(FrameLease(frame, lambda: released.append(True)), 42)
        assert gen._overview_future is not None
        assert gen._viewport_task is not None
        await gen._overview_future
        await gen._viewport_task
    finally:
        gen.close()

    assert released == [True]
    by_layer = {source.header.layer: source for source in captured}
    overview = by_layer[PreviewLayer.OVERVIEW]
    viewport = by_layer[PreviewLayer.VIEWPORT]
    assert overview.header.camera_id == viewport.header.camera_id == "camera-1"
    assert overview.header.source_stream_id == viewport.header.source_stream_id
    assert overview.header.frame_idx == viewport.header.frame_idx == 42
    assert overview.header.width == 204
    assert overview.header.source_rect_px.model_dump() == {"x": 0, "y": 0, "width": 230, "height": 180}


async def test_reset_stream_changes_capture_identity() -> None:
    captured: list[PreviewFrame] = []
    gen = _gen(sink=captured.append, uid="camera-1")
    try:
        gen.submit_frame(_frame(w=32, h=24), 0)
        assert gen._overview_future is not None
        await gen._overview_future
        await asyncio.sleep(0)  # allow the future's publish callback to run
        first = captured[-1]
        source_stream_id = gen.reset_stream()
        gen.submit_frame(_frame(w=32, h=24), 0)
        assert gen._overview_future is not None
        await gen._overview_future
        await asyncio.sleep(0)
        second = captured[-1]
    finally:
        gen.close()

    assert first.header.source_stream_id != second.header.source_stream_id == source_stream_id
