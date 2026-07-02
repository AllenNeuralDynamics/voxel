"""Base classes for pyramid buffer implementations."""

from abc import ABC, abstractmethod
from concurrent.futures import Future
from enum import IntEnum

import numpy as np
from pydantic import BaseModel, Field, computed_field
from vxlib.vec import UIVec3D

from ome_zarr_writer.dataset import Dtype, ScaleLevel


class BufferStage(IntEnum):
    """Buffer lifecycle stages.

    Lifecycle: IDLE → COLLECTING → PROCESSING → IDLE
               (any stage can transition to ERROR on failure)
    """

    ERROR = -1
    IDLE = 0
    COLLECTING = 1
    PROCESSING = 2


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


class BufferSlot(ABC):
    """Abstract base for a ring buffer slot that collects frames and downsamples.

    Implementations differ in storage (numpy arrays vs SharedMemory) and
    execution model (threads vs processes for downsampling).

    The writer manages the lifecycle:
    1. assign_batch(idx) — prepare for collection
    2. add_frame() repeatedly — fill L0 data
    3. start_processing() — begin async downsampling, returns a Future
    4. future.result() — wait for completion
    5. writer calls backend.write_batch() — flush to storage
    6. reset() — ready for next batch
    """

    def __init__(self, name: str, shape_l0: UIVec3D, max_level: ScaleLevel, dtype: Dtype):
        self.name = name
        self.shape_l0 = shape_l0
        self.max_level = max_level
        self._dtype = dtype.dtype
        self.filled_l0 = 0
        self.batch_idx: int | None = None

    @property
    @abstractmethod
    def stage(self) -> BufferStage: ...

    @abstractmethod
    def add_frame(self, frame: np.ndarray, z_idx: int) -> None:
        """Add a frame at the given Z index in the L0 volume."""

    @abstractmethod
    def get_volume(self, level: ScaleLevel) -> np.ndarray:
        """Get the numpy array for a scale level. L0 is always available; other levels require processing."""

    @abstractmethod
    def start_processing(self) -> Future:
        """Begin pyramid downsampling asynchronously. Returns a Future that resolves when done."""

    @abstractmethod
    def close(self) -> None:
        """Release all resources (arrays, executors, shared memory)."""

    def assign_batch(self, batch_idx: int) -> None:
        """Prepare buffer for a new batch."""
        self.batch_idx = batch_idx
        self.filled_l0 = 0

    def get_status(self) -> BufferStatus:
        """Get current status."""
        return BufferStatus(
            batch_idx=self.batch_idx,
            stage=self.stage,
            filled=self.filled_l0,
            capacity=self.shape_l0.z,
        )
