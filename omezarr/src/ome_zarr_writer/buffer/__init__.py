"""Ring buffer implementations for streaming pyramid generation."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import StrEnum

from vxlib.vec import UIVec3D

from ome_zarr_writer.types import Dtype, ScaleLevel

from ._base import BufferSlot, BufferStage, BufferStatus
from ._process import ProcessBufferSlot
from ._threaded import ThreadedBufferSlot

__all__ = [
    "BufferSlot",
    "BufferStage",
    "BufferStatus",
    "ProcessBufferSlot",
    "PyramidRingBuffer",
    "ThreadedBufferSlot",
]

MIN_CPU_COUNT_FOR_MULTIPROCESS = 12


class PyramidRingBuffer(StrEnum):
    """Factory + identifier for a ring of pyramid-downsampling slots.

    Each member is simultaneously:
    - a string (for configs/logging): `str(PyramidRingBuffer.THREADED) == "threaded"`
    - a factory: `PyramidRingBuffer.THREADED(slots=3, prefix="ring", ...)` returns
      a `list[BufferSlot]` — the ring itself.

    Invoking a member creates all N slots in parallel via a small thread pool.
    """

    _cls: type[BufferSlot]  # instance attribute declaration; set in __new__

    THREADED = "threaded", ThreadedBufferSlot
    PROCESS = "process", ProcessBufferSlot

    def __new__(cls, value: str, buffer_cls: type[BufferSlot]) -> "PyramidRingBuffer":
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj._cls = buffer_cls
        return obj

    def __call__(
        self,
        slots: int,
        prefix: str,
        shape_l0: UIVec3D,
        max_level: ScaleLevel,
        dtype: Dtype,
    ) -> list[BufferSlot]:
        """Construct a ring of `slots` buffer slots of this mode, in parallel.

        Args:
            slots: Number of buffer slots in the ring (minimum 2).
            prefix: Name prefix for each slot (each gets `{prefix}_{idx}`).
            shape_l0: Shape of the L0 volume per batch (z, y, x).
            max_level: Maximum pyramid level to allocate.
            dtype: Data type for the arrays.
        """

        def create_single(slot_idx: int) -> tuple[int, BufferSlot]:
            buf = self._cls(
                name=f"{prefix}_{slot_idx}",
                shape_l0=shape_l0,
                max_level=max_level,
                dtype=dtype,
            )
            return slot_idx, buf

        buffers_dict: dict[int, BufferSlot] = {}
        with ThreadPoolExecutor(max_workers=min(slots, 8)) as executor:
            futures = {executor.submit(create_single, i): i for i in range(slots)}
            for future in as_completed(futures):
                slot_idx, buf = future.result()
                buffers_dict[slot_idx] = buf

        return [buffers_dict[i] for i in range(slots)]

    @staticmethod
    def by_cpu_count(n: int) -> "PyramidRingBuffer":
        """Factory method to choose buffer mode based on CPU count."""
        if n >= MIN_CPU_COUNT_FOR_MULTIPROCESS:
            return PyramidRingBuffer.PROCESS
        return PyramidRingBuffer.THREADED
