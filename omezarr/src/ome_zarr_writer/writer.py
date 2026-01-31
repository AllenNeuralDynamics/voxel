import numpy as np
from pydantic import BaseModel, Field, computed_field
from collections.abc import Callable

from vxlib.vec import UIVec3D

from ome_zarr_writer.types import Dtype, ScaleLevel
from .config import WriterConfig
from ome_zarr_writer.backends.base import Backend
from .buffer import BufferStage, BufferStatus, MultiScaleBuffer, create_ring_buffer
import time
from rich import print


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
    """
    Performance tracker for streaming acquisition.

    Tracks FPS and throughput with both cumulative and instantaneous metrics.
    Designed for use within StreamingWriter but can also be used standalone
    for custom acquisition loops.

    Example standalone usage:
        >>> metrics = StreamMetrics(frame_bytes=512*512*2)
        >>> for frame in camera:
        ...     process(frame)
        ...     metrics.tick()
        ...     print(f"FPS: {metrics.fps:.1f}, Throughput: {metrics.throughput_gbs:.2f} GB/s")

    Args:
        frame_bytes: Size of each frame in bytes
    """

    def __init__(self, frame_bytes: int):
        """
        Initialize performance tracker.

        Args:
            frame_bytes: Size of each frame in bytes
        """
        self.frame_bytes = frame_bytes
        self.start_time = time.perf_counter()
        self.frame_count = 0
        self.total_bytes = 0

        # For instantaneous metrics (window-based)
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
        """Total elapsed time since start (seconds)."""
        return time.perf_counter() - self.start_time

    @property
    def fps(self) -> float:
        """Cumulative frames per second since start."""
        return self.frame_count / self.elapsed if self.elapsed > 0 else 0.0

    @property
    def fps_inst(self) -> float:
        """Instantaneous FPS since last window reset."""
        elapsed = time.perf_counter() - self._window_start
        return self._window_frames / elapsed if elapsed > 0 else 0.0

    @property
    def throughput_gbs(self) -> float:
        """Cumulative throughput in GB/s since start."""
        return (self.total_bytes / 1e9) / self.elapsed if self.elapsed > 0 else 0.0

    @property
    def throughput_gbs_inst(self) -> float:
        """Instantaneous throughput in GB/s since last window reset."""
        elapsed = time.perf_counter() - self._window_start
        return (self._window_bytes / 1e9) / elapsed if elapsed > 0 else 0.0

    def __repr__(self) -> str:
        return (
            f"StreamMetrics(frames={self.frame_count}, fps={self.fps:.1f}, throughput={self.throughput_gbs:.2f} GB/s)"
        )


class OMEZarrWriter:
    def __init__(
        self,
        backend: Backend,
        slots: int = 3,
        status_callback: Callable[[StreamStatus], None] | None = None,
        status_interval: float = 1.0,
    ) -> None:
        """
        Initialize the streaming writer.

        Args:
            backend: Backend instance (contains cfg)
            slots: Number of buffer slots in the ring (minimum 2)
            status_callback: Called periodically with status updates.
                           Default: prints to console with rich formatting.
                           None: silent (no auto-reporting).
            status_interval: How often to call status_callback (seconds)
        """
        if slots < 2:
            raise ValueError("Ring buffer requires at least 2 slots")

        self.backend = backend
        # self.cfg = backend.cfg  # Extract config from writer
        self.slots = slots

        # Create buffer shape for each batch
        self.batch_shape = UIVec3D(
            z=self.cfg.batch_z,
            y=self.cfg.volume_shape.y,
            x=self.cfg.volume_shape.x,
        )

        # Initialize ring of buffers with callback
        self.buffers = create_ring_buffer(
            slots=slots,
            prefix="ring",
            shape_l0=self.batch_shape,
            max_level=self.cfg.max_level,
            dtype=self.cfg.dtype,
            flush_callback=self._batch_flush_callback,  # Async callback
        )

        # Track state
        self._global_z = 0  # Absolute z position in full volume
        self._current_slot = 0  # Active buffer index
        self._batch_number = 0  # Current batch index

        # Assign first buffer to batch 0
        self.buffers[self._current_slot].assign_batch_index(0)

        # Status reporting configuration
        self._status_callback = status_callback or self._default_status_callback
        self._status_interval = status_interval
        self._last_status_time = time.perf_counter()

        # Create performance tracker
        frame_bytes = backend.cfg.volume_shape.y * backend.cfg.volume_shape.x * backend.cfg.dtype.dtype.itemsize
        self._perf = StreamMetrics(frame_bytes)

    @property
    def cfg(self):
        return self.backend.cfg

    def _default_status_callback(self, status: StreamStatus) -> None:
        """Default callback: print formatted status to console."""
        from rich import print

        print(f"  [cyan]{status.summary()}[/cyan]")

    def _batch_flush_callback(self, buffer: MultiScaleBuffer) -> bool:
        """
        Callback when buffer downsampling completes (called from processing thread).
        Called synchronously from the buffer's processing task.

        The buffer is in FLUSHING state when this is called.

        Returns:
            True on success, False on failure
        """
        if buffer.batch_idx is None:
            return False

        try:
            # Write batch synchronously (buffer is already in async task)
            success = self.backend.write_batch(buffer)
            return success
        except Exception as e:
            print(f"Error writing batch {buffer.batch_idx}: {e}")
            return False

    @property
    def current_buffer(self) -> MultiScaleBuffer:
        """Get the currently active buffer."""
        return self.buffers[self._current_slot]

    @property
    def latest_frame(self) -> np.ndarray:
        """Get the most recently added frame."""
        if self._global_z == 0:
            raise RuntimeError("No frames have been added yet")

        # The last frame is in the current buffer at (filled_l0 - 1)
        buf = self.current_buffer
        z_in_buffer = buf.filled_l0 - 1
        return buf.get_volume(ScaleLevel.L0)[z_in_buffer, :, :]

    def add_frame(self, frame: np.ndarray) -> None:
        """
        Add a frame to the pipeline.

        Automatically:
        - Tracks performance metrics
        - Reports status at configured interval
        - Rotates buffers when needed
        - Triggers async downsampling and writing

        Args:
            frame: 2D numpy array (Y, X) to add
        """
        if self._global_z >= self.cfg.volume_shape.z:
            raise RuntimeError(f"Volume complete: cannot add more frames ({self._global_z}/{self.cfg.volume_shape.z})")

        # Get current buffer and local z index
        buf = self.current_buffer
        z_in_buffer = self._global_z % self.cfg.batch_z

        # Add frame to current buffer (triggers async processing when full)
        buf.add_frame(frame, z_in_buffer)

        # Increment global counter
        self._global_z += 1

        # Auto-tick performance tracker
        self._perf.tick()

        # Auto-report status if interval elapsed
        now = time.perf_counter()
        if now - self._last_status_time >= self._status_interval:
            if self._status_callback:
                self._status_callback(self.get_status())
            self._last_status_time = now
            self._perf.reset_window()  # Reset instantaneous window

        # Check if we need to rotate to next buffer
        if self._global_z % self.cfg.batch_z == 0 and self._global_z < self.cfg.volume_shape.z:
            self._rotate_buffer()

    def _rotate_buffer(self) -> None:
        """
        Rotate to the next buffer slot.

        This is non-blocking - we only check if the next buffer is available.
        If it's still being processed/written, we wait (this indicates insufficient slots).
        """
        # Move to next slot
        self._current_slot = (self._current_slot + 1) % self.slots
        self._batch_number += 1

        next_buf = self.buffers[self._current_slot]

        # Check if next buffer is available
        if next_buf.stage != BufferStage.IDLE:
            # Buffer is still busy - wait for it to complete
            # This indicates we need more slots for this acquisition rate
            print(
                f"[bold yellow]Waiting for buffer slot {self._current_slot} (stage={next_buf.stage.name})[/bold yellow]"
            )
            next_buf.wait_ready()

        # Assign the new batch index and prepare for collection
        next_buf.assign_batch_index(self._batch_number)

    def get_buffer_for_batch(self, batch_idx: int) -> MultiScaleBuffer | None:
        """Get the buffer containing a specific batch, if available and downsampled."""
        for buf in self.buffers:
            # Buffer must have completed downsampling (FLUSHING or IDLE, not COLLECTING/DOWNSAMPLING)
            if buf.batch_idx == batch_idx and buf.stage not in (BufferStage.COLLECTING, BufferStage.DOWNSAMPLING):
                return buf
        return None

    def wait_all(self) -> None:
        """Wait for all buffers to complete processing (downsampling + flushing)."""
        for buf in self.buffers:
            buf.wait_ready()

    def _flush_partials(self):
        for buf in self.buffers:
            if buf.stage == BufferStage.COLLECTING and buf.filled_l0 > 0:
                buf.flush_all()

    # def abort(self):
    #     self._flush_partials()
    #     self.wait_all()
    #     for buf in self.buffers:
    #         buf.close()
    #     self.writer.close()

    def close(self) -> None:
        """Close all buffers, writer, and clean up resources."""
        # First, finish processing any partial buffers
        for buf in self.buffers:
            if buf.stage == BufferStage.COLLECTING and buf.filled_l0 > 0:
                buf.flush_all()

        # Wait for all processing and writing to complete
        self.wait_all()

        # Clean up buffers
        for buf in self.buffers:
            buf.close()

        # Close writer
        self.backend._finalize()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        self.close()

    def get_status(self) -> StreamStatus:
        """
        Get current unified status snapshot.

        Returns:
            StreamStatus with complete pipeline state including performance metrics
        """
        buffer_statuses = {
            i: BufferStatus(
                batch_idx=buf.batch_idx,
                stage=buf.stage,
                filled=buf.filled_l0,
                capacity=buf.shape_l0.z,
            )
            for i, buf in enumerate(self.buffers)
        }

        # Estimate remaining time
        estimated_remaining = None
        if self._perf.fps > 0:
            frames_left = self.cfg.volume_shape.z - self._global_z
            estimated_remaining = frames_left / self._perf.fps

        return StreamStatus(
            # Performance metrics
            fps=self._perf.fps,
            fps_inst=self._perf.fps_inst,
            throughput_gbs=self._perf.throughput_gbs,
            throughput_gbs_inst=self._perf.throughput_gbs_inst,
            frames_acquired=self._perf.frame_count,
            # Progress
            global_z=self._global_z,
            total_frames=self.cfg.volume_shape.z,
            frames_remaining=self.cfg.volume_shape.z - self._global_z,
            # Batches
            current_batch=self._batch_number,
            total_batches=self.cfg.num_batches,
            # Buffers
            current_slot=self._current_slot,
            buffers=buffer_statuses,
            # Timing
            elapsed_time=self._perf.elapsed,
            estimated_remaining=estimated_remaining,
        )

    def __repr__(self) -> str:
        return (
            f"StreamingWriter(slots={self.slots}, "
            f"batch_shape={self.batch_shape}, "
            f"progress={self._global_z}/{self.cfg.volume_shape.z})"
        )


# Example usage:
if __name__ == "__main__":
    from rich import print
    from ome_zarr_writer.backends.log import LogBackend

    # Create configuration
    print("\n[bold cyan]Testing StreamingWriter with LogBackend[/bold cyan]")
    v_shape = UIVec3D(z=2048, y=2048, x=2048)
    max_level = ScaleLevel.L5
    c_shape = max_level.chunk_shape
    s_shape = WriterConfig.compute_shard_shape_from_target(
        v_shape=v_shape,
        c_shape=c_shape,
        dtype=Dtype.UINT16,
        target_shard_gb=0.05,
    )

    cfg = WriterConfig(
        name="test_acq5",
        volume_shape=v_shape,
        shard_shape=s_shape,
        chunk_shape=c_shape,
        dtype=Dtype.UINT16,
        max_level=max_level,
        batch_z_shards=1,
    )

    print(f"Config: batch_z={cfg.batch_z}, num_batches={cfg.num_batches}")
    print(f"Volume shape: {cfg.volume_shape}")
    print(f"Dataset name: {cfg.name}")

    # Create LogBackend for testing (lightweight, no actual I/O)
    backend = LogBackend(cfg, storage_root="./tmp")
    print(f"\n[green]Created LogBackend at {backend.log_path}[/green]")

    # Use context manager for automatic cleanup
    with OMEZarrWriter(backend, slots=3) as writer:
        print("\n[yellow]Adding frames...[/yellow]")

        # Add frames
        for z in range(min(50, cfg.volume_shape.z)):
            frame = np.random.randint(0, 1000, (cfg.volume_shape.y, cfg.volume_shape.x), dtype=np.uint16)
            writer.add_frame(frame)

            if (z + 1) % cfg.batch_z == 0:
                print(f"  Completed batch {(z + 1) // cfg.batch_z}, current slot: {writer._current_slot}")

        print(f"\n[green]Added {writer._global_z} frames[/green]")

        # Get status
        status = writer.get_status()
        print("\n[yellow]Acquisition Status:[/yellow]")
        print(f"  Progress: {status.progress_percent:.1f}% ({status.global_z}/{status.total_frames} frames)")
        print(f"  Batches written: {backend._batch_count}/{status.total_batches}")
        print(f"  Frames remaining: {status.frames_remaining}")

        print("\n[yellow]Buffer Slots:[/yellow]")
        for slot_id, slot_status in status.buffers.items():
            active_marker = " [ACTIVE]" if slot_status.is_active else ""
            batch_info = f"batch_{slot_status.batch_idx}" if slot_status.batch_idx is not None else "unassigned"
            print(
                f"  Slot {slot_id} ({batch_info}): {slot_status.stage} - "
                f"{slot_status.filled}/{slot_status.capacity} "
                f"({slot_status.fill_percent:.1f}%){active_marker}"
            )

    print("\n[green]Test complete! All resources cleaned up.[/green]")
    print(f"[cyan]Written {backend._batch_count} batches to {backend.storage_root}[/cyan]")
