import asyncio
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import partial
from uuid import uuid4

import numpy as np
from ome_zarr_writer import FrameLease

from .protocol import PreviewFrame, PreviewLayer, PreviewViewport, ValidBits

OVERVIEW_WIDTH = 2048  # overview output width (the overview is the main view)
RENDER_CAP = 2048  # max width of a single coherent viewport-image render (rendered on demand, not per frame)
# Fraction each axis grows beyond the viewport so small pans stay covered without a re-render. Its area cost
# is quadratic in 1 + 2*margin, so keep it small while retaining a little coverage during interaction.
OVERSCAN_MARGIN = 0.05


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


class _PreviewSource:
    """One full-resolution source whose final release closes an optional writer lease."""

    def __init__(self, frame: np.ndarray | FrameLease) -> None:
        self.array = frame.array if isinstance(frame, FrameLease) else frame
        self._lease = frame if isinstance(frame, FrameLease) else None
        self._references = 1
        self._lock = threading.Lock()

    def retain(self) -> "_PreviewSource":
        with self._lock:
            if self._references <= 0:
                raise RuntimeError("preview source is closed")
            self._references += 1
        return self

    def release(self) -> None:
        lease: FrameLease | None = None
        with self._lock:
            if self._references <= 0:
                raise RuntimeError("preview source released too many times")
            self._references -= 1
            if self._references == 0:
                lease, self._lease = self._lease, None
        if lease is not None:
            lease.close()


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
        self._current_source: _PreviewSource | None = None
        self._current_valid_bits: ValidBits = 16

        self._viewport_task: asyncio.Task[None] | None = None
        self._overview_future: _OverviewFuture | None = None
        self._overview_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PreviewOverview")
        self._viewport_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PreviewViewport")

        self.health = PreviewHealth()

    def set_viewport(self, viewport: PreviewViewport, *, regenerate: bool = False) -> asyncio.Task[None] | None:
        self._viewport = viewport
        if regenerate and self._current_source is not None:
            return self._schedule_viewport(
                self._current_source,
                self._frame_idx,
                viewport,
                valid_bits=self._current_valid_bits,
                source_stream_id=self._source_stream_id,
            )
        return None

    def submit_frame(self, frame: np.ndarray | FrameLease, idx: int, *, valid_bits: ValidBits = 16) -> None:
        """Process a new raw frame: dispatch overview and viewport work in the background.

        The viewport uses cancel-stale (latest viewport invalidates prior work). Overview
        uses skip-if-busy — if the previous overview hasn't finished, drop this
        frame's preview rather than queueing. Returns immediately so callers
        (preview loop, acquisition grab loop) are not gated by preview work.
        """
        source = _PreviewSource(frame)
        previous = self._current_source
        self._frame_idx = idx
        self._current_source = source
        self._current_valid_bits = valid_bits
        source_stream_id = self._source_stream_id

        self._schedule_viewport(
            source,
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
            overview_source = source.retain()
            concurrent_future = self._overview_executor.submit(
                partial(
                    PreviewFrame.from_source,
                    overview_source.array,
                    camera_id=self._camera_id,
                    source_stream_id=source_stream_id,
                    layer=PreviewLayer.OVERVIEW,
                    frame_idx=idx,
                    viewport=PreviewViewport(),
                    target_width=self._target_width,
                    valid_bits=valid_bits,
                ),
            )
            concurrent_future.add_done_callback(lambda _: overview_source.release())
            self._overview_future = asyncio.wrap_future(concurrent_future, loop=loop)
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
        if previous is not None:
            previous.release()

    def reset_stream(self) -> str:
        """Start and return a new camera capture identity."""
        self.cancel_pending()
        self.clear_frame()
        self._source_stream_id = uuid4().hex
        return self._source_stream_id

    def clear_frame(self) -> None:
        """Release the retained latest full-resolution source without changing stream identity."""
        source, self._current_source = self._current_source, None
        if source is not None:
            source.release()

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
        self.clear_frame()
        self._overview_executor.shutdown(wait=False, cancel_futures=True)
        self._viewport_executor.shutdown(wait=False, cancel_futures=True)

    def _cancel_viewport_task(self) -> None:
        """Cancel the current viewport render and discard its result."""
        if self._viewport_task is not None and not self._viewport_task.done():
            self._viewport_task.cancel()
        self._viewport_task = None

    def _schedule_viewport(
        self,
        source: _PreviewSource,
        frame_idx: int,
        viewport: PreviewViewport,
        *,
        valid_bits: ValidBits,
        source_stream_id: str,
    ) -> asyncio.Task[None] | None:
        work_epoch = self._work_epoch
        self._cancel_viewport_task()

        if not viewport.needs_adjustment:
            return None

        render_viewport = viewport.expanded(OVERSCAN_MARGIN)
        viewport_source = source.retain()
        concurrent_future = self._viewport_executor.submit(
            partial(
                PreviewFrame.from_source,
                viewport_source.array,
                camera_id=self._camera_id,
                source_stream_id=source_stream_id,
                layer=PreviewLayer.VIEWPORT,
                frame_idx=frame_idx,
                viewport=render_viewport,
                target_width=RENDER_CAP,
                valid_bits=valid_bits,
            )
        )
        concurrent_future.add_done_callback(lambda _: viewport_source.release())

        async def generate_and_send() -> None:
            try:
                viewport_frame = await asyncio.wrap_future(concurrent_future)
            except asyncio.CancelledError:
                return
            if work_epoch != self._work_epoch:
                return
            self._sink(viewport_frame)

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
