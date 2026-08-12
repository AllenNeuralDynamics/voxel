"""Atomic, bounded subscriptions to a station's materialized state.

All feed mutation and connection setup are serialized through one asyncio lock.
A connection's initial view therefore represents exactly the cursor immediately
before its queued views; there is no subscribe-after-snapshot gap.
"""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from vxl.preview import LatestFrameQueue, PreviewEmission, PreviewSourceEmission, StationPreviewFramePacket
from vxlib import Emitter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable
    from typing import Self

    from vxl.system import StationInfo
    from vxlib import Readable, Subscribable

from .models import StationFeedView, StationState, StationStatus, StreamCursor


def _unix_time_us() -> int:
    return time.time_ns() // 1_000


class StationFeedLaggedError(RuntimeError):
    """Raised in a connection whose bounded update buffer overflowed."""


@dataclass(frozen=True)
class _Termination:
    error: Exception | None = None


class _ConnectionState:
    def __init__(self, update_buffer_size: int) -> None:
        self._queue: asyncio.Queue[StationFeedView | _Termination] = asyncio.Queue(maxsize=update_buffer_size)
        self._termination: _Termination | None = None
        self._termination_delivered = False

    async def next(self) -> StationFeedView:
        if self._termination_delivered:
            raise StopAsyncIteration

        item = await self._queue.get()
        if isinstance(item, _Termination):
            self._termination_delivered = True
            if item.error is not None:
                raise item.error
            raise StopAsyncIteration
        return item

    def offer(self, view: StationFeedView) -> bool:
        try:
            self._queue.put_nowait(view)
        except asyncio.QueueFull:
            return False
        return True

    def terminate(self, error: Exception | None = None) -> None:
        if self._termination is not None:
            return
        termination = _Termination(error)
        self._termination = termination
        while not self._queue.empty():
            self._queue.get_nowait()
        self._queue.put_nowait(termination)


class StationFeedConnection:
    """An atomic initial view followed by later complete, strictly ordered views."""

    def __init__(
        self,
        initial: StationFeedView,
        *,
        state: _ConnectionState,
        disconnect: "Callable[[StationFeedConnection], Awaitable[None]]",
    ) -> None:
        self.initial = initial
        self._state = state
        self._disconnect = disconnect

    def __aiter__(self) -> "Self":
        return self

    async def __anext__(self) -> StationFeedView:
        return await self._state.next()

    async def close(self) -> None:
        """Unregister this connection. Safe to call more than once."""
        await self._disconnect(self)


class StationFeed:
    """Publish station state and preview without depending on a transport.

    A slow connection is removed when its bounded buffer fills. Its iterator
    raises :class:`StationFeedLaggedError`, after which the consumer reconnects
    to receive a fresh complete view.
    """

    def __init__(
        self,
        station: "StationInfo",
        source: "Readable[StationState]",
        *,
        update_buffer_size: int = 64,
    ) -> None:
        if update_buffer_size < 1:
            raise ValueError("update_buffer_size must be at least 1")
        self._station = station
        self._state = source.value
        self._stream_id = uuid.uuid4().hex
        self._seq = 0
        self._frame_seq = 0
        self._frames = Emitter[PreviewEmission]()
        self._frame_queue = LatestFrameQueue()
        self._frame_task: asyncio.Task[None] | None = None
        self._update_buffer_size = update_buffer_size
        self._connections: dict[StationFeedConnection, _ConnectionState] = {}
        self._lock = asyncio.Lock()
        self._closed = False
        self._unsubscribe = source.subscribe(self._on_state)

    @property
    def frames(self) -> "Subscribable[PreviewEmission]":
        """Lossy preview packets stamped against the reliable station-state timeline."""
        return self._frames

    def clear_preview(self) -> None:
        """Discard queued preview work when the active session ends."""
        self._frame_queue.clear()
        if self._frame_task is not None:
            self._frame_task.cancel()
            self._frame_task = None

    async def publish_preview(self, emission: PreviewSourceEmission) -> None:
        """Stamp and enqueue one source frame from the active station session."""
        channel_id, layer, frame = emission
        async with self._lock:
            if self._closed or self._state.status is not StationStatus.ACTIVE or self._state.session is None:
                return
            frame_seq = self._frame_seq
            self._frame_seq += 1
            packet = StationPreviewFramePacket.wrap(
                frame,
                channel_id=channel_id,
                seq=frame_seq,
                state_cursor=self._cursor_unlocked(),
                stamped_at_unix_us=_unix_time_us(),
            ).pack()
            self._frame_queue.put((channel_id, layer), packet)
            if self._frame_task is None or self._frame_task.done():
                self._frame_task = asyncio.create_task(self._drain_frames(), name="station-preview-delivery")

    @asynccontextmanager
    async def connect(self) -> "AsyncGenerator[StationFeedConnection]":
        """Atomically capture an initial view and register for all later views."""
        connection = await self._connect()
        try:
            yield connection
        finally:
            await connection.close()

    async def snapshot(self) -> StationFeedView:
        """Return the latest complete view for a one-shot query."""
        async with self._lock:
            return self._view_unlocked()

    async def _on_state(self, state: StationState) -> None:
        """Materialize one committed reactive station-state change."""
        async with self._lock:
            if self._closed:
                return
            if state == self._state:
                return

            self._state = state
            self._seq += 1
            view = self._view_unlocked()
            lagged: list[tuple[StationFeedConnection, _ConnectionState]] = []
            for connection, connection_state in self._connections.items():
                if not connection_state.offer(view):
                    lagged.append((connection, connection_state))
            for connection, connection_state in lagged:
                del self._connections[connection]
                connection_state.terminate(
                    StationFeedLaggedError(
                        f"station feed connection fell behind at {view.cursor.stream_id}:{view.cursor.seq}"
                    )
                )

    async def _drain_frames(self) -> None:
        """Deliver latest-only packets without propagating consumer delay to Instrument."""
        while not self._closed:
            (channel_id, layer), packet = await self._frame_queue.get()
            await self._frames.emit((channel_id, layer, packet))

    async def close(self) -> None:
        """Close the feed and end all active connection iterators."""
        self._unsubscribe()
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            states = tuple(self._connections.values())
            self._connections.clear()
            for state in states:
                state.terminate()
        self.clear_preview()

    async def _connect(self) -> StationFeedConnection:
        async with self._lock:
            if self._closed:
                raise RuntimeError("station feed is closed")
            state = _ConnectionState(self._update_buffer_size)
            connection = StationFeedConnection(
                self._view_unlocked(),
                state=state,
                disconnect=self._disconnect,
            )
            self._connections[connection] = state
            return connection

    async def _disconnect(self, connection: StationFeedConnection) -> None:
        async with self._lock:
            state = self._connections.pop(connection, None)
            if state is not None:
                state.terminate()

    def _cursor_unlocked(self) -> StreamCursor:
        return StreamCursor(stream_id=self._stream_id, seq=self._seq)

    def _view_unlocked(self) -> StationFeedView:
        return StationFeedView(
            cursor=self._cursor_unlocked(),
            observed_at_unix_us=_unix_time_us(),
            station=self._station,
            status=self._state.status,
            session=self._state.session,
            error=self._state.error,
        )


__all__ = ["StationFeed", "StationFeedConnection", "StationFeedLaggedError"]
