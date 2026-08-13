"""How much RAM a ring slot really costs, and the bounds on ring depth.

This lives beside the code that incurs the cost — :class:`~ome_zarr_writer.slot.BatchSlot` allocates the
shared memory, :func:`~ome_zarr_writer.pyramid.pyramids_3d_numba` allocates the worker's temporaries — so
the model cannot silently drift from the implementation it is modelling.

Budget *policy* deliberately stays with the caller: this package has no view of the machine's RAM or how
it is shared between consumers. What it does own is the vocabulary — the cost model, the depth bounds,
and the failures a ``sizer`` may signal back to :meth:`OMEZarrWriter.begin_stack`.
"""

from vxlib.vec import UIVec3D

from vxlib import Dtype

from .dataset import ScaleLevel

# Ring depth: at least 2, so collect overlaps downsample/flush; capped because coordination and cache
# pressure outweigh the gains beyond it.
MIN_SLOTS = 2
MAX_SLOTS = 4


class RingSizingError(RuntimeError):
    """A ring could not be sized. Raised by a ``sizer`` passed to :meth:`OMEZarrWriter.begin_stack`."""


class RingBudgetExceededError(RingSizingError):
    """The geometry cannot fit :data:`MIN_SLOTS` within the caller's memory budget.

    Deterministic — the same config against the same budget always fails, so the config is what has to
    change: ``batch_z_shards``, ``shard_z_chunks``, ``max_level``, ``target_shard_gb``, frame size, or
    whatever sets the caller's budget.
    """


class RingMemoryUnavailableError(RingSizingError):
    """The budget allows the ring, but the machine cannot currently supply the memory.

    Transient — something else is holding it. Kept distinct from :class:`RingBudgetExceededError` so
    "this config is too big" and "this machine is busy right now" are not the same failure.
    """


_F32_ITEMSIZE = 4  # pyramids_3d_numba reduces into float32 regardless of the store dtype


def _voxels(shape: UIVec3D) -> int:
    return shape.z * shape.y * shape.x


def per_slot_bytes(batch_shape: UIVec3D, max_level: ScaleLevel, dtype: Dtype) -> int:
    """Peak RAM one ring slot needs, in bytes.

    A slot costs more than the shared memory it owns. While its worker flushes a batch it also holds
    private buffers that never live in the ring:

    - shared memory — L0 plus every pyramid level at ``dtype`` (``BatchSlot.__init__``)
    - worker heap — L1..Lmax as float32, all live at once (``pyramids_3d_numba`` returns them together)
    - worker heap — one ``.astype()`` copy per level, largest at L1 (``_worker_process_and_write``)

    Counting only the shared memory under-counts by ~36% for uint16 and ~61% for uint8, which
    over-allocates slots and exhausts RAM mid-acquisition.

    The worker terms are charged to every slot, not just the flushing ones. In steady state one slot
    collects while the rest flush, so this over-reserves by at most one slot's transient — cheap next to
    crashing a run that is hours in.
    """
    shm = 0
    worker_pyramid = 0
    worker_cast = 0
    for level in max_level.levels:
        voxels = _voxels(level.scale(batch_shape))
        shm += voxels * dtype.itemsize
        if level != ScaleLevel.L0:
            worker_pyramid += voxels * _F32_ITEMSIZE
            worker_cast = max(worker_cast, voxels * dtype.itemsize)  # one level at a time; L1 is largest
    return shm + worker_pyramid + worker_cast


def ring_shm_bytes(slots: int, batch_shape: UIVec3D, max_level: ScaleLevel, dtype: Dtype) -> int:
    """Resident shared memory a ring of ``slots`` holds — the part that stays allocated between volumes.

    Smaller than ``slots * per_slot_bytes(...)``, which also counts the workers' transient buffers.
    """
    per_slot_shm = sum(_voxels(level.scale(batch_shape)) * dtype.itemsize for level in max_level.levels)
    return slots * per_slot_shm


def slots_for_budget(
    batch_shape: UIVec3D,
    max_level: ScaleLevel,
    dtype: Dtype,
    *,
    budget_bytes: int,
    available_bytes: int | None = None,
    label: str = "",
) -> int:
    """Deepest ring this geometry can fill within ``budget_bytes``, clamped to the ring-depth bounds.

    Callers supply only the two numbers this package cannot know — how many bytes they are entitled to,
    and (optionally) how many the machine can actually supply right now. The cost model, the bounds, and
    the failure modes stay here, so no caller has to re-derive them.

    ``budget_bytes`` is entitlement, a policy figure; ``available_bytes`` is reality. Keeping them apart
    is what lets "this config is too big for its share" and "this machine is busy" be different failures.
    Pass ``available_bytes=None`` to skip the reality check.

    Raises:
        RingBudgetExceededError: fewer than :data:`MIN_SLOTS` fit the budget. One slot would serialize
            collect against flush, so there is no usable ring below that.
        RingMemoryUnavailableError: the budget allows the ring but the machine cannot back it. This is a
            floor, not a guarantee — free memory is an estimate and can change before the allocation
            lands.
    """
    prefix = f"{label}: " if label else ""
    slot_bytes = per_slot_bytes(batch_shape, max_level, dtype)
    max_slots = budget_bytes // slot_bytes if slot_bytes else 0
    if max_slots < MIN_SLOTS:
        raise RingBudgetExceededError(
            f"{prefix}cannot fit {MIN_SLOTS} batch slots ({slot_bytes:,} B/slot, {budget_bytes:,} B budget). "
            f"Reduce batch_z_shards, shard_z_chunks, max_level, target_shard_gb, or the frame size; "
            f"or raise the budget."
        )
    slots = min(max_slots, MAX_SLOTS)
    needed = slots * slot_bytes
    if available_bytes is not None and available_bytes < needed:
        raise RingMemoryUnavailableError(
            f"{prefix}{slots} batch slots need {needed:,} B but only {available_bytes:,} B is free. "
            f"Another process is using this machine's memory."
        )
    return slots
