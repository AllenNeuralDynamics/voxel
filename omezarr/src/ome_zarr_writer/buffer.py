from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import IntEnum
from multiprocessing import Lock, Value, shared_memory
from multiprocessing.sharedctypes import Synchronized

import numpy as np
from pydantic import BaseModel, Field, computed_field
from rich import print

from ome_zarr_writer.pyramid import pyramids_3d
from vxlib.vec import UIVec3D

from ome_zarr_writer.types import Dtype, ScaleLevel


@dataclass(frozen=True)
class ShmArray:
    """RAII-style wrapper over a shared memory block + NumPy view."""

    name: str
    shape: tuple[int, int, int]
    dtype: np.dtype
    nbytes: int

    # non-frozen internals for lifetime mgmt (process-local view)
    _shm: shared_memory.SharedMemory | None = None
    _owns: bool = False

    @staticmethod
    def create(shape: tuple[int, int, int], dtype: np.dtype, name: str) -> "ShmArray":
        dtype = np.dtype(dtype)
        nbytes = int(np.prod(shape)) * dtype.itemsize
        shm = shared_memory.SharedMemory(create=True, size=nbytes, name=name)
        arr = np.ndarray(shape, dtype=dtype, buffer=shm.buf, order="C")
        arr[:] = 0  # zero for safety but migh make it slower to initialize buffers
        return ShmArray(name=shm.name, shape=shape, dtype=dtype, nbytes=nbytes, _shm=shm, _owns=True)

    @staticmethod
    def attach(name: str, shape: tuple[int, int, int], dtype: np.dtype) -> "ShmArray":
        dtype = np.dtype(dtype)
        nbytes = int(np.prod(shape)) * dtype.itemsize
        shm = shared_memory.SharedMemory(name=name, create=False)
        return ShmArray(name=name, shape=shape, dtype=dtype, nbytes=nbytes, _shm=shm, _owns=False)

    @property
    def view(self) -> np.ndarray:
        if self._shm is None:
            raise RuntimeError("SharedMemory not attached")
        return np.ndarray(self.shape, dtype=self.dtype, buffer=self._shm.buf, order="C")

    def close(self) -> None:
        if self._shm is not None:
            self._shm.close()
            if self._owns:
                # Only the creator should unlink the block
                self._shm.unlink()


class BufferStage(IntEnum):
    """
    Buffer lifecycle stages.

    Lifecycle: IDLE → COLLECTING → DOWNSAMPLING → FLUSHING → IDLE
               (any stage can transition to ERROR on failure)
    """

    ERROR = -1
    IDLE = 0
    COLLECTING = 1
    DOWNSAMPLING = 2
    FLUSHING = 3


class BufferStatus(BaseModel):
    """Status information for a single buffer slot in the ring."""

    batch_idx: int | None = Field(None, description="Batch index this buffer represents")
    stage: BufferStage = Field(..., description="Current stage of the buffer")
    filled: int = Field(..., ge=0, description="Number of frames filled")
    capacity: int = Field(..., gt=0, description="Total capacity of the buffer")

    @computed_field
    @property
    def fill_percent(self) -> float:
        """Percentage of buffer filled."""
        return (self.filled / self.capacity) * 100 if self.capacity > 0 else 0.0

    @computed_field
    @property
    def is_active(self) -> bool:
        """Whether this buffer is actively collecting frames."""
        return self.stage == BufferStage.COLLECTING


class MultiScaleBuffer:
    def __init__(
        self,
        name: str,
        shape_l0: UIVec3D,
        max_level: ScaleLevel,
        dtype: Dtype,
        flush_callback: Callable[["MultiScaleBuffer"], bool] | None = None,
    ):
        self.name: str = name
        self.dtype: np.dtype = dtype.dtype
        self.max_level: ScaleLevel = max_level
        self.shape_l0: UIVec3D = shape_l0
        self.filled_l0 = 0
        self.batch_idx: int | None = None  # Track which batch this buffer represents
        self._flush_callback = flush_callback  # Callback when READY

        self._stage: Synchronized[int] = Value("i", BufferStage.IDLE)

        self.lock = Lock()

        self.shm: dict[ScaleLevel, ShmArray] = {}
        for level in self.max_level.levels:
            shp = level.scale(self.shape_l0)
            # shp = self.shape_l0.scale(level.factor)
            self.shm[level] = ShmArray.create((shp.z, shp.y, shp.x), self.dtype, f"{name}_{level}")

        self._executor = ThreadPoolExecutor(max_workers=4)

        self._futures: Future | None = None

    @property
    def stage(self) -> BufferStage:
        return BufferStage(self._stage.value)

    @stage.setter
    def stage(self, value: BufferStage):
        self._stage.value = int(value)

    def get_volume(self, level: ScaleLevel) -> np.ndarray:
        """
        Get the volume data for a specific scale level.

        L0 can be accessed at any time. Other levels require downsampling to be complete.
        """
        if level != ScaleLevel.L0 and self.stage in (BufferStage.IDLE, BufferStage.COLLECTING):
            msg = f"Unable to get volume at level {level}: Buffer not yet downsampled (stage={self.stage.name})"
            raise ValueError(msg)
        return self.shm[level].view

    def add_frame(self, frame: np.ndarray, z_idx: int):
        _, y0, x0 = self.shape_l0
        if frame.shape != (y0, x0):
            raise ValueError(f"Frame shape {frame.shape} does not match L0 frame {(y0, x0)}")
        if z_idx < 0 or z_idx >= self.shape_l0.z:
            raise IndexError(f"z_abs {z_idx} is outside L0 depth {self.shape_l0.z}")

        with self.lock:
            self.shm[ScaleLevel.L0].view[z_idx, :y0, :x0] = frame.astype(self.dtype, copy=False)
            self.filled_l0 = max(self.filled_l0, z_idx + 1)
            if self.filled_l0 == self.shape_l0.z:
                self._start_processing()

    def _start_processing(self):
        """Start async processing of pyramids. Call with lock held."""

        def _process_pyramids_task():
            """Compute multi-scale downsampling and flush to storage."""
            try:
                # Phase 1: Downsampling
                self.stage = BufferStage.DOWNSAMPLING
                block: np.ndarray = self.shm[ScaleLevel.L0].view[
                    : min(self.shape_l0.z, self.filled_l0)
                ]  # direct shared-memory slice

                # Compute pyramids using new API
                pyramid: dict[ScaleLevel, np.ndarray] = pyramids_3d(block, self.max_level)

                for level, vol_fx in pyramid.items():
                    shm_shape = self.shm[level].shape
                    data_shape = vol_fx.shape
                    z_max = min(shm_shape[0], data_shape[0])
                    y_max = min(shm_shape[1], data_shape[1])
                    x_max = min(shm_shape[2], data_shape[2])
                    self.shm[level].view[:z_max, :y_max, :x_max] = vol_fx[:z_max, :y_max, :x_max].astype(self.dtype)

                # Phase 2: Flushing (if callback registered)
                if self._flush_callback is not None:
                    self.stage = BufferStage.FLUSHING
                    success = self._flush_callback(self)  # Callback should return bool

                    if success:
                        self.stage = BufferStage.IDLE  # Ready for reuse
                    else:
                        self.stage = BufferStage.ERROR
                else:
                    # No callback - just mark as idle
                    self.stage = BufferStage.IDLE

            except Exception as e:
                print(f"Error processing buffer {self.name} batch {self.batch_idx}: {e}")
                self.stage = BufferStage.ERROR

        self._futures = self._executor.submit(_process_pyramids_task)

    def flush_all(self):
        """
        Manually trigger processing for partial buffers.
        Useful when buffer isn't full but needs to be processed (e.g., end of volume).
        """
        with self.lock:
            if self.filled_l0 > 0 and self.stage == BufferStage.COLLECTING:
                self._start_processing()

    def wait_ready(self):
        """Wait for processing to complete and buffer to be READY."""
        if self._futures is not None:
            self._futures.result()  # Block until done

    def assign_batch_index(self, batch_idx: int) -> None:
        """
        Assign a batch index to this buffer and prepare it for collection.

        Args:
            batch_idx: The batch index this buffer will represent
        """
        with self.lock:
            self.batch_idx = batch_idx
            self.filled_l0 = 0
            self.stage = BufferStage.COLLECTING

    def get_status(self) -> BufferStatus:
        """
        Get the status of this buffer.

        Returns:
            BufferStatus: Status information for this buffer
        """
        with self.lock:
            return BufferStatus(
                batch_idx=self.batch_idx,
                stage=self.stage,
                filled=self.filled_l0,
                capacity=self.shape_l0.z,
            )

    def close(self) -> None:
        for s in self.shm.values():
            s.close()


def create_ring_buffer(
    slots: int,
    prefix: str,
    shape_l0: UIVec3D,
    max_level: ScaleLevel,
    dtype: Dtype,
    flush_callback: Callable[[MultiScaleBuffer], bool],
) -> list[MultiScaleBuffer]:
    """
    Create ring buffer slots in parallel.

    Each buffer allocation is independent and can be done concurrently.
    This significantly speeds up initialization when allocating large buffers.
    """

    def create_single_buffer(slot_idx: int) -> tuple[int, MultiScaleBuffer]:
        """Create a single buffer and return its index and instance."""
        buf = MultiScaleBuffer(
            name=f"{prefix}_{slot_idx}",
            shape_l0=shape_l0,
            max_level=max_level,
            dtype=dtype,
            flush_callback=flush_callback,
        )
        return slot_idx, buf

    # Create buffers in parallel
    buffers_dict: dict[int, MultiScaleBuffer] = {}

    with ThreadPoolExecutor(max_workers=min(slots, 8)) as executor:
        # Submit all buffer creation tasks
        futures = {executor.submit(create_single_buffer, i): i for i in range(slots)}

        # Collect results as they complete
        for future in as_completed(futures):
            slot_idx, buf = future.result()
            buffers_dict[slot_idx] = buf
            print(f"[magenta]Buffer {slot_idx + 1}/{slots} initialized[/magenta]")

    # Return buffers in correct order
    return [buffers_dict[i] for i in range(slots)]


# Example usage:
if __name__ == "__main__":
    from rich import print

    # Test ShmArray
    print("[bold cyan]Testing ShmArray...[/bold cyan]")
    shmc_array = ShmArray.create((100, 100, 100), np.dtype(np.float32), "my_array")
    shmc_array.view[:] = np.random.rand(*shmc_array.shape)

    shma_array = ShmArray.attach("my_array", shmc_array.shape, shmc_array.dtype)
    print(f"Mean [green]parent={shmc_array.view.mean():.4f}, child={shma_array.view.mean():.4f}[/green]")

    shmc_array.close()
    shma_array.close()
