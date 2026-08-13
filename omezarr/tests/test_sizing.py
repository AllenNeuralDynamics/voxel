"""Ring sizing: the per-slot cost model, and when the writer is allowed to ask for a new size.

The cost model is the budget's only view of what a slot actually consumes, and the "when" is what keeps
a reused ring from being re-validated against a RAM figure it already spent. Both have produced
production bugs, so both are pinned here.
"""

from pathlib import Path

import numpy as np
import pytest
from ome_zarr_writer import Local, OMEZarrWriter, ScaleLevel, WriterConfig
from ome_zarr_writer.sizing import (
    MAX_SLOTS,
    MIN_SLOTS,
    RingBudgetExceededError,
    RingMemoryUnavailableError,
    RingSizingError,
    per_slot_bytes,
    ring_shm_bytes,
    slots_for_budget,
)
from vxlib.vec import UIVec3D, UVec3D

from vxlib import Dtype


def _cfg(y: int = 64, x: int = 64, z: int = 32, level: ScaleLevel = ScaleLevel.L2) -> WriterConfig:
    return WriterConfig(
        volume_shape=UIVec3D(z=z, y=y, x=x),
        voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
        max_level=level,
    )


# ── Cost model ──────────────────────────────────────────────────────────────────


def test_per_slot_bytes_counts_shm_plus_worker_buffers() -> None:
    """The model is shm (L0 + tail) + the worker's float32 pyramid + its largest cast temporary."""
    shape = UIVec3D(z=8, y=64, x=64)
    level = ScaleLevel.L2
    dtype = Dtype.UINT16

    shm = expected_f32 = 0
    cast_peak = 0
    for lv in level.levels:
        s = lv.scale(shape)
        voxels = s.z * s.y * s.x
        shm += voxels * dtype.itemsize
        if lv != ScaleLevel.L0:
            expected_f32 += voxels * 4
            cast_peak = max(cast_peak, voxels * dtype.itemsize)

    assert per_slot_bytes(shape, level, dtype) == shm + expected_f32 + cast_peak


def test_per_slot_bytes_exceeds_the_shared_memory_it_budgets_for() -> None:
    """The bug this guards: budgeting only the ring under-counts, so slots get over-allocated."""
    shape, level = UIVec3D(z=128, y=2048, x=2048), ScaleLevel.L7
    for dtype, low, high in ((Dtype.UINT16, 1.30, 1.40), (Dtype.UINT8, 1.55, 1.65)):
        ratio = per_slot_bytes(shape, level, dtype) / ring_shm_bytes(1, shape, level, dtype)
        assert low < ratio < high, f"{dtype}: per-slot/shm ratio {ratio:.3f} outside [{low}, {high}]"


def test_per_slot_bytes_scales_with_batch_depth_and_dtype() -> None:
    level = ScaleLevel.L2
    single = per_slot_bytes(UIVec3D(z=8, y=64, x=64), level, Dtype.UINT16)
    assert per_slot_bytes(UIVec3D(z=16, y=64, x=64), level, Dtype.UINT16) == 2 * single
    # uint8 halves the shm and cast terms but not the float32 pyramid, so it is more than half.
    assert single / 2 < per_slot_bytes(UIVec3D(z=8, y=64, x=64), level, Dtype.UINT8) < single


def test_ring_shm_bytes_is_linear_in_slots() -> None:
    shape, level, dtype = UIVec3D(z=8, y=64, x=64), ScaleLevel.L2, Dtype.UINT16
    one = ring_shm_bytes(1, shape, level, dtype)
    assert ring_shm_bytes(4, shape, level, dtype) == 4 * one


def test_slot_bounds_are_sane() -> None:
    assert MIN_SLOTS >= 2, "one slot would serialize collect against flush"
    assert MAX_SLOTS >= MIN_SLOTS


# ── Budget → depth, and the two ways it can fail ────────────────────────────────

_SHAPE, _LEVEL, _DTYPE = UIVec3D(z=8, y=64, x=64), ScaleLevel.L2, Dtype.UINT16
_SLOT = per_slot_bytes(_SHAPE, _LEVEL, _DTYPE)


def test_slots_for_budget_clamps_between_the_bounds() -> None:
    assert slots_for_budget(_SHAPE, _LEVEL, _DTYPE, budget_bytes=_SLOT * MIN_SLOTS) == MIN_SLOTS
    assert slots_for_budget(_SHAPE, _LEVEL, _DTYPE, budget_bytes=_SLOT * 1000) == MAX_SLOTS


def test_budget_too_small_raises_a_deterministic_failure() -> None:
    """Config-is-too-big: same inputs always fail, so the message points at the config."""
    with pytest.raises(RingBudgetExceededError, match="cannot fit"):
        slots_for_budget(_SHAPE, _LEVEL, _DTYPE, budget_bytes=_SLOT * MIN_SLOTS - 1)


def test_machine_too_busy_raises_a_distinct_transient_failure() -> None:
    """Machine-is-busy: the budget allows the ring, but the memory is not there right now."""
    budget = _SLOT * MIN_SLOTS
    with pytest.raises(RingMemoryUnavailableError, match="is free"):
        slots_for_budget(_SHAPE, _LEVEL, _DTYPE, budget_bytes=budget, available_bytes=budget - 1)


def test_the_two_failures_are_separately_catchable() -> None:
    """The point of two types: a caller can retry a busy machine but must not retry a bad config."""
    assert issubclass(RingBudgetExceededError, RingSizingError)
    assert issubclass(RingMemoryUnavailableError, RingSizingError)
    assert not issubclass(RingMemoryUnavailableError, RingBudgetExceededError)
    assert issubclass(RingSizingError, RuntimeError)  # existing `except RuntimeError` handlers still catch


def test_availability_check_is_opt_in() -> None:
    """Callers with no view of free memory (benchmarks, tests) skip the reality check."""
    assert slots_for_budget(_SHAPE, _LEVEL, _DTYPE, budget_bytes=_SLOT * MIN_SLOTS, available_bytes=None) == MIN_SLOTS


def test_label_identifies_the_consumer_in_the_message() -> None:
    """Channels size concurrently, so a bare failure would not say which camera raised it."""
    with pytest.raises(RingBudgetExceededError, match="cam-左: cannot fit"):
        slots_for_budget(_SHAPE, _LEVEL, _DTYPE, budget_bytes=1, label="cam-左")


# ── When the writer asks for a size ─────────────────────────────────────────────


@pytest.mark.slow
def test_sizer_runs_only_when_the_ring_is_allocated(tmp_path: Path) -> None:
    """The regression guard: a reused ring must not be re-sized.

    Re-checking a RAM budget on the reuse path once failed a run at its second volume — the first
    volume's ring was still resident, so the budget it had already spent counted against it, and the
    writer refused a ring it was about to reuse unchanged without allocating a byte.
    """
    calls: list[UIVec3D] = []

    def sizer(config: WriterConfig) -> int:
        calls.append(config.batch_shape)
        return MIN_SLOTS

    cfg = _cfg()
    writer = OMEZarrWriter()
    try:
        writer.begin_stack(cfg, Local(target=tmp_path / "v1"), sizer=sizer)
        writer.end_stack()
        assert len(calls) == 1, "first volume must size the ring it allocates"

        # Same geometry → the ring is reused, so nothing is allocated and nothing is sized.
        writer.begin_stack(cfg, Local(target=tmp_path / "v2"), sizer=sizer)
        writer.end_stack()
        assert len(calls) == 1, "reusing a ring must not consult the sizer"

        # Changed geometry → the ring is rebuilt, so the new size is chosen against the new config.
        wider = _cfg(y=128, x=128)
        writer.begin_stack(wider, Local(target=tmp_path / "v3"), sizer=sizer)
        writer.end_stack()
        assert len(calls) == 2, "a geometry change must re-size the ring"
        assert calls[-1] == wider.batch_shape
    finally:
        writer.close()


@pytest.mark.slow
def test_sizer_determines_ring_depth(tmp_path: Path) -> None:
    """The sizer's return value wins over the constructor default, and applies per allocation."""
    cfg = _cfg()
    writer = OMEZarrWriter(slots=MAX_SLOTS)
    try:
        writer.begin_stack(cfg, Local(target=tmp_path / "v1"), sizer=lambda _: MIN_SLOTS)
        assert writer._ring is not None
        assert len(writer._ring) == MIN_SLOTS
        writer.end_stack()
    finally:
        writer.close()


def test_writer_rejects_a_sizer_that_returns_too_few_slots(tmp_path: Path) -> None:
    """The floor is enforced at the library boundary, not left to each sizer to remember."""
    writer = OMEZarrWriter()
    try:
        with pytest.raises(RingSizingError, match="at least"):
            writer.begin_stack(_cfg(), Local(target=tmp_path / "v1"), sizer=lambda _: MIN_SLOTS - 1)
    finally:
        writer.close()


@pytest.mark.slow
def test_sizer_is_optional_and_falls_back_to_constructor_slots(tmp_path: Path) -> None:
    """Callers that pin slots explicitly (benchmarks, examples) keep working untouched."""
    cfg = _cfg()
    writer = OMEZarrWriter(slots=MIN_SLOTS)
    try:
        writer.begin_stack(cfg, Local(target=tmp_path / "v1"))
        assert writer._ring is not None
        assert len(writer._ring) == MIN_SLOTS
        for i in range(cfg.volume_shape.z):
            writer.add_frame(np.full((cfg.volume_shape.y, cfg.volume_shape.x), i + 1, dtype=np.uint16))
        writer.end_stack()
    finally:
        writer.close()
