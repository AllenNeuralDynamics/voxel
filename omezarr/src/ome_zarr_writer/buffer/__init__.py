"""Ring buffer implementations for streaming pyramid generation."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

from vxlib.vec import UIVec3D

from ome_zarr_writer.types import Dtype, ScaleLevel

from ._base import BufferStage, BufferStatus, PyramidBuffer
from ._threaded import ThreadedBuffer

__all__ = [
    "BufferStage",
    "BufferStatus",
    "PyramidBuffer",
    "ThreadedBuffer",
    "create_ring_buffer",
]

BufferMode = Literal["threaded", "process"]

BUFFER_CLASSES: dict[str, type[PyramidBuffer]] = {
    "threaded": ThreadedBuffer,
}


def create_ring_buffer(
    slots: int,
    prefix: str,
    shape_l0: UIVec3D,
    max_level: ScaleLevel,
    dtype: Dtype,
    mode: BufferMode = "threaded",
) -> list[PyramidBuffer]:
    """Create ring buffer slots in parallel.

    Args:
        slots: Number of buffer slots (minimum 2).
        prefix: Name prefix for each slot.
        shape_l0: Shape of L0 volume per batch (z, y, x).
        max_level: Maximum pyramid level.
        dtype: Data type for the arrays.
        mode: Buffer implementation — "threaded" (numpy arrays) or "process" (SharedMemory).
    """
    buffer_cls = BUFFER_CLASSES.get(mode)
    if buffer_cls is None:
        raise ValueError(f"Unknown buffer mode '{mode}'. Available: {list(BUFFER_CLASSES)}")

    def create_single(slot_idx: int) -> tuple[int, PyramidBuffer]:
        buf = buffer_cls(
            name=f"{prefix}_{slot_idx}",
            shape_l0=shape_l0,
            max_level=max_level,
            dtype=dtype,
        )
        return slot_idx, buf

    buffers_dict: dict[int, PyramidBuffer] = {}
    with ThreadPoolExecutor(max_workers=min(slots, 8)) as executor:
        futures = {executor.submit(create_single, i): i for i in range(slots)}
        for future in as_completed(futures):
            slot_idx, buf = future.result()
            buffers_dict[slot_idx] = buf

    return [buffers_dict[i] for i in range(slots)]
