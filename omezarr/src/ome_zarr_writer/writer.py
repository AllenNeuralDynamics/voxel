import logging
import time
from collections.abc import Callable
from concurrent.futures import Future

import numpy as np
from pydantic import BaseModel, Field, computed_field
from vxlib.vec import UIVec3D

from ome_zarr_writer.backends.base import Backend
from ome_zarr_writer.buffer import BufferSlot, BufferStage, BufferStatus, PyramidRingBuffer
from ome_zarr_writer.types import ScaleLevel

log = logging.getLogger(__name__)


class StreamStatus(BaseModel):
    """Complete streaming acquisition status snapshot."""

    # Performance metrics
    fps: float = Field(..., description="Cumulative frames per second")
    fps_inst: float = Field(..., description="Instantaneous FPS")
    throughput_gbs: float = Field(..., description="Cumulative throughput (GB/s)")
    throughput_gbs_inst: float = Field(..., description="Instantaneous throughput (GB/s)")
    frames_acquired: int = Field(..., description="Total frames acquired")

    # Progress (from Pipeline)
    global_z: int = Field(..., ge=0, description="Current global frame index")
    total_frames: int = Field(..., gt=0, description="Total frames in volume")
    frames_remaining: int = Field(..., ge=0, description="Frames remaining")

    # Batches (from Pipeline)
    current_batch: int = Field(..., ge=0, description="Current batch index")
    total_batches: int = Field(..., gt=0, description="Total number of batches")

    # Buffers (from Pipeline)
    current_slot: int = Field(..., ge=0, description="Active buffer slot index")
    buffers: dict[int, BufferStatus] = Field(..., description="Status of each buffer slot")

    # Timing
    elapsed_time: float = Field(..., ge=0, description="Elapsed time (seconds)")
    estimated_remaining: float | None = Field(None, description="Estimated time remaining (seconds)")

    @computed_field
    @property
    def progress_percent(self) -> float:
        """Overall progress percentage."""
        return (self.global_z / self.total_frames) * 100 if self.total_frames > 0 else 0.0

    @computed_field
    @property
    def is_complete(self) -> bool:
        """Whether all frames have been collected."""
        return self.global_z >= self.total_frames

    def summary(self) -> str:
        """One-line summary for quick reporting."""
        return (
            f"Frame {self.global_z}/{self.total_frames} ({self.progress_percent:.1f}%) | "
            f"Batch {self.current_batch}/{self.total_batches} | "
            f"FPS: {self.fps:.1f} (inst: {self.fps_inst:.1f}) | "
            f"Throughput: {self.throughput_gbs:.2f} GB/s"
        )

    @classmethod
    def empty(cls, target_frames: int) -> "StreamStatus":
        return cls(
            fps=0,
            fps_inst=0,
            throughput_gbs=0,
            throughput_gbs_inst=0,
            frames_acquired=0,
            global_z=0,
            total_frames=target_frames,
            frames_remaining=target_frames,
            estimated_remaining=0,
            current_batch=0,
            total_batches=1,
            current_slot=0,
            buffers={},
            elapsed_time=0,
        )


class StreamMetrics:
    """Performance tracker for streaming acquisition."""

    def __init__(self, frame_bytes: int):
        self.frame_bytes = frame_bytes
        self.start_time = time.perf_counter()
        self.frame_count = 0
        self.total_bytes = 0
        self._window_start = self.start_time
        self._window_frames = 0
        self._window_bytes = 0

    def tick(self) -> None:
        """Record a frame acquisition event."""
        self.frame_count += 1
        self.total_bytes += self.frame_bytes
        self._window_frames += 1
        self._window_bytes += self.frame_bytes

    def reset_window(self) -> None:
        """Reset instantaneous measurement window."""
        self._window_start = time.perf_counter()
        self._window_frames = 0
        self._window_bytes = 0

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.start_time

    @property
    def fps(self) -> float:
        return self.frame_count / self.elapsed if self.elapsed > 0 else 0.0

    @property
    def fps_inst(self) -> float:
        elapsed = time.perf_counter() - self._window_start
        return self._window_frames / elapsed if elapsed > 0 else 0.0

    @property
    def throughput_gbs(self) -> float:
        return (self.total_bytes / 1e9) / self.elapsed if self.elapsed > 0 else 0.0

    @property
    def throughput_gbs_inst(self) -> float:
        elapsed = time.perf_counter() - self._window_start
        return (self._window_bytes / 1e9) / elapsed if elapsed > 0 else 0.0


class OMEZarrWriter:
    def __init__(
        self,
        backend: Backend,
        channel_index: int = 0,
        slots: int = 6,
        buffer_mode: PyramidRingBuffer | str = PyramidRingBuffer.PROCESS,
        status_callback: Callable[[StreamStatus], None] | None = None,
        status_interval: float = 5.0,
    ) -> None:
        """Initialize the streaming writer.

        Args:
            backend: Backend instance (contains cfg)
            channel_index: Channel index this writer writes to in the (C, Z, Y, X) array
            slots: Number of buffer slots in the ring (minimum 2)
            buffer_mode: Ring-buffer factory — accepts a `PyramidRingBuffer`
                member or the equivalent string ("threaded" | "process"). Cast
                to the enum immediately at the start of __init__.
            status_callback: Called periodically with status updates.
                           Default: prints to console with rich formatting.
                           None: silent (no auto-reporting).
            status_interval: How often to call status_callback (seconds)
        """
        if slots < 2:
            raise ValueError("Ring buffer requires at least 2 slots")

        self.backend = backend
        self.channel_index = channel_index
        self.slots = slots
        self.buffer_mode = PyramidRingBuffer(buffer_mode)

        # Create buffer shape for each batch
        self.batch_shape = UIVec3D(
            z=self.cfg.batch_z,
            y=self.cfg.volume_shape.y,
            x=self.cfg.volume_shape.x,
        )

        # Initialize ring of buffers via the mode's factory.
        self.buffers = self.buffer_mode(
            slots=slots,
            prefix="ring",
            shape_l0=self.batch_shape,
            max_level=self.cfg.max_level,
            dtype=self.cfg.dtype,
        )

        # Track state
        self._global_z = 0
        self._current_slot = 0
        self._batch_number = 0
        self._pending: dict[int, Future] = {}  # slot_idx → processing future

        # Assign first buffer to batch 0
        self.buffers[self._current_slot].assign_batch(0)

        # Status reporting
        self._status_callback = status_callback or self._default_status_callback
        self._status_interval = status_interval
        self._last_status_time = time.perf_counter()

        # Performance tracker
        frame_bytes = backend.cfg.volume_shape.y * backend.cfg.volume_shape.x * backend.cfg.dtype.dtype.itemsize
        self._perf = StreamMetrics(frame_bytes)

    @property
    def cfg(self):
        return self.backend.cfg

    def _default_status_callback(self, status: StreamStatus) -> None:
        log.info(status.summary())

    def _flush_slot(self, slot_idx: int) -> None:
        """Wait for a slot's processing to complete and flush to backend."""
        if slot_idx not in self._pending:
            return
        future = self._pending.pop(slot_idx)
        future.result()  # wait for downsampling
        buf = self.buffers[slot_idx]
        success = self.backend.write_batch(buf, channel_index=self.channel_index)
        if not success:
            log.warning("batch %d write failed", buf.batch_idx)

    @property
    def current_buffer(self) -> BufferSlot:
        return self.buffers[self._current_slot]

    @property
    def latest_frame(self) -> np.ndarray:
        if self._global_z == 0:
            raise RuntimeError("No frames have been added yet")
        buf = self.current_buffer
        z_in_buffer = buf.filled_l0 - 1
        return buf.get_volume(ScaleLevel.L0)[z_in_buffer, :, :]

    def add_frame(self, frame: np.ndarray) -> None:
        """Add a frame to the pipeline.

        Automatically tracks performance, reports status, rotates buffers,
        and triggers async downsampling.
        """
        if self._global_z >= self.cfg.volume_shape.z:
            raise RuntimeError(f"Volume complete: cannot add more frames ({self._global_z}/{self.cfg.volume_shape.z})")

        buf = self.current_buffer
        z_in_buffer = self._global_z % self.cfg.batch_z

        buf.add_frame(frame, z_in_buffer)
        self._global_z += 1
        self._perf.tick()

        # Auto-report status
        now = time.perf_counter()
        if now - self._last_status_time >= self._status_interval:
            if self._status_callback:
                self._status_callback(self.get_status())
            self._last_status_time = now
            self._perf.reset_window()

        # Buffer full — start processing and rotate
        if self._global_z % self.cfg.batch_z == 0 and self._global_z < self.cfg.volume_shape.z:
            future = buf.start_processing()
            self._pending[self._current_slot] = future
            self._rotate_buffer()

    def _rotate_buffer(self) -> None:
        """Rotate to the next buffer slot, flushing if necessary."""
        next_slot = (self._current_slot + 1) % self.slots
        self._batch_number += 1

        # If next slot has a pending future, flush it first
        if next_slot in self._pending:
            self._flush_slot(next_slot)

        self._current_slot = next_slot
        self.buffers[self._current_slot].assign_batch(self._batch_number)

    def get_buffer_for_batch(self, batch_idx: int) -> BufferSlot | None:
        """Get the buffer containing a specific batch, if available."""
        for buf in self.buffers:
            if buf.batch_idx == batch_idx and buf.stage == BufferStage.IDLE:
                return buf
        return None

    def close(self) -> None:
        """Close all buffers, flush pending, and clean up resources."""
        # Start processing the current partial buffer if it has data
        buf = self.current_buffer
        if buf.filled_l0 > 0 and buf.stage == BufferStage.COLLECTING:
            future = buf.start_processing()
            self._pending[self._current_slot] = future

        # Flush all pending slots
        for slot_idx in list(self._pending):
            self._flush_slot(slot_idx)

        # Clean up
        for buf in self.buffers:
            buf.close()
        self.backend._finalize()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get_status(self) -> StreamStatus:
        buffer_statuses = {i: buf.get_status() for i, buf in enumerate(self.buffers)}

        estimated_remaining = None
        if self._perf.fps > 0:
            frames_left = self.cfg.volume_shape.z - self._global_z
            estimated_remaining = frames_left / self._perf.fps

        return StreamStatus(
            fps=self._perf.fps,
            fps_inst=self._perf.fps_inst,
            throughput_gbs=self._perf.throughput_gbs,
            throughput_gbs_inst=self._perf.throughput_gbs_inst,
            frames_acquired=self._perf.frame_count,
            global_z=self._global_z,
            total_frames=self.cfg.volume_shape.z,
            frames_remaining=self.cfg.volume_shape.z - self._global_z,
            current_batch=self._batch_number,
            total_batches=self.cfg.num_batches,
            current_slot=self._current_slot,
            buffers=buffer_statuses,
            elapsed_time=self._perf.elapsed,
            estimated_remaining=estimated_remaining,
        )

    def __repr__(self) -> str:
        return (
            f"OMEZarrWriter(slots={self.slots}, "
            f"batch_shape={self.batch_shape}, "
            f"progress={self._global_z}/{self.cfg.volume_shape.z})"
        )
