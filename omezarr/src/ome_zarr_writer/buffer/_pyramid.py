"""Multi-scale pyramid generation for the buffer package.

Two backends, same result up to floating-point rounding:

- `pyramids_3d_numba`: JIT-compiled kernels, parameterized by `reduction`
  ("mean"/"max") and `parallel` (whether the kernel uses numba's prange thread
  pool). Primary path in production.
- `pyramids_3d_numpy`: pure-numpy reductions via reshape + mean/max. Kept as a
  reference implementation and fallback when numba is unavailable.

For the numba path the kernel bodies are written once per reduction and
JIT-specialized twice (serial + parallel) at module import. `prange` on the
outermost loop degenerates to `range` under `@jit(parallel=False)`, so a single
source supports both variants without duplication.

Buffers pick the right numba variant for their execution model:
- ThreadedBufferSlot calls parallel=False (multiple Python threads may call concurrently)
- ProcessBufferSlot's worker calls parallel=True (single Python caller per worker process)
"""

import math
from collections.abc import Callable
from typing import Literal

import numpy as np
from numba import jit, prange

from ome_zarr_writer.dataset import ScaleLevel

Reduction = Literal["mean", "max"]


# ---------------------------------------------------------------------------
# Kernel bodies — one per reduction, JIT-specialized below. Written with
# prange on the outermost loop so the same source compiles to both a serial
# kernel (parallel=False → prange acts as range) and a parallel kernel
# (parallel=True → prange dispatches to numba's thread pool).
# ---------------------------------------------------------------------------


def _kernel_3d_mean(vol: np.ndarray, out: np.ndarray) -> None:
    """2×2×2 box-average reduction: out[t, i, j] = mean of the 8 covering voxels."""
    T_out, H_out, W_out = out.shape
    for t in prange(T_out):
        for i in range(H_out):
            for j in range(W_out):
                t2 = t * 2
                i2 = i * 2
                j2 = j * 2
                s = 0.0
                for dt in range(2):
                    for di in range(2):
                        for dj in range(2):
                            s += vol[t2 + dt, i2 + di, j2 + dj]
                out[t, i, j] = s * 0.125


def _kernel_3d_max(vol: np.ndarray, out: np.ndarray) -> None:
    """2×2×2 max-projection reduction: out[t, i, j] = max of the 8 covering voxels."""
    T_out, H_out, W_out = out.shape
    for t in prange(T_out):
        for i in range(H_out):
            for j in range(W_out):
                t2 = t * 2
                i2 = i * 2
                j2 = j * 2
                m = vol[t2, i2, j2]
                for dt in range(2):
                    for di in range(2):
                        for dj in range(2):
                            v = vol[t2 + dt, i2 + di, j2 + dj]
                            if v > m:
                                m = v
                out[t, i, j] = m


# ---------------------------------------------------------------------------
# JIT specialization — each kernel is compiled twice, once serial, once
# parallel. Compilation is lazy (first call per signature) and cached on disk.
# ---------------------------------------------------------------------------

_jit_serial = jit(nopython=True, parallel=False, fastmath=True, cache=True)
_jit_parallel = jit(nopython=True, parallel=True, fastmath=True, cache=True)

_KERNELS: dict[tuple[Reduction, bool], Callable[[np.ndarray, np.ndarray], None]] = {
    ("mean", False): _jit_serial(_kernel_3d_mean),
    ("mean", True): _jit_parallel(_kernel_3d_mean),
    ("max", False): _jit_serial(_kernel_3d_max),
    ("max", True): _jit_parallel(_kernel_3d_max),
}


# ---------------------------------------------------------------------------
# Orchestration — one implementation, parameterized by reduction and whether
# the inner kernel should parallelize across threads.
# ---------------------------------------------------------------------------


def pyramids_3d_numba(
    block: np.ndarray,
    max_level: ScaleLevel,
    reduction: Reduction = "mean",
    parallel: bool = False,
) -> dict[ScaleLevel, np.ndarray]:
    """Compute a 3D multi-scale pyramid via chained 2×2×2 reductions.

    Args:
        block: L0 input volume with shape (Z, Y, X). Any numeric dtype — internally
            upcast to float32 for the reduction.
        max_level: Highest pyramid level to compute. All levels L1..max_level are
            produced; L0 is not included in the returned dict (it's the input).
        reduction: "mean" for standard box averaging, "max" for max projection.
        parallel: If True, the inner kernel uses numba's prange thread pool. Safe
            only when there is a single Python caller (e.g., inside a worker
            process). Must be False when multiple Python threads may call
            concurrently.

    Returns:
        Mapping of each non-L0 level to its reduced float32 volume.
    """
    kernel = _KERNELS[(reduction, parallel)]

    results: dict[ScaleLevel, np.ndarray] = {}
    levels = [level for level in max_level.levels if level != ScaleLevel.L0]
    sorted_levels = sorted(levels, key=lambda x: x.factor)

    current_factor = 1
    current_vol = block.astype(np.float32, copy=False)

    for target_level in sorted_levels:
        target_factor = target_level.factor
        steps_needed = int(math.log2(target_factor)) - int(math.log2(current_factor))

        for _ in range(steps_needed):
            z, y, x = current_vol.shape
            z2, y2, x2 = (z // 2) * 2, (y // 2) * 2, (x // 2) * 2
            if min(z2, y2, x2) == 0:
                break
            out = np.empty((z2 // 2, y2 // 2, x2 // 2), dtype=np.float32)
            kernel(current_vol[:z2, :y2, :x2], out)
            current_vol = out
            current_factor *= 2

        z_out = block.shape[0] // target_factor
        y_out = block.shape[1] // target_factor
        x_out = block.shape[2] // target_factor
        results[target_level] = current_vol[:z_out, :y_out, :x_out]

    return results


# ---------------------------------------------------------------------------
# Pure-numpy reference implementation. No JIT, no thread pool. Intended as a
# fallback when numba is unavailable, or as a sanity-check during testing.
# ---------------------------------------------------------------------------


def pyramids_3d_numpy(
    block: np.ndarray,
    max_level: ScaleLevel,
    reduction: Reduction = "mean",
) -> dict[ScaleLevel, np.ndarray]:
    """Compute a 3D multi-scale pyramid using pure numpy reductions.

    Same semantics as `pyramids_3d_numba` but implemented via `reshape` plus
    `ndarray.mean` / `ndarray.max`. No `parallel` parameter because numpy has
    no equivalent knob — internal parallelism depends on the linked BLAS/LAPACK
    and is not user-controllable here.

    Args:
        block: L0 input volume with shape (Z, Y, X). Any numeric dtype — internally
            upcast to float32 for the reduction.
        max_level: Highest pyramid level to compute. All levels L1..max_level are
            produced; L0 is not included in the returned dict (it's the input).
        reduction: "mean" for standard box averaging, "max" for max projection.

    Returns:
        Mapping of each non-L0 level to its reduced float32 volume.
    """
    results: dict[ScaleLevel, np.ndarray] = {}
    levels = [level for level in max_level.levels if level != ScaleLevel.L0]
    sorted_levels = sorted(levels, key=lambda x: x.factor)

    current_factor = 1
    current_vol = block.astype(np.float32, copy=False)

    for target_level in sorted_levels:
        target_factor = target_level.factor
        steps_needed = int(math.log2(target_factor)) - int(math.log2(current_factor))

        for _ in range(steps_needed):
            z, y, x = current_vol.shape
            z2, y2, x2 = (z // 2) * 2, (y // 2) * 2, (x // 2) * 2
            if min(z2, y2, x2) == 0:
                break
            reshaped = current_vol[:z2, :y2, :x2].reshape(z2 // 2, 2, y2 // 2, 2, x2 // 2, 2)
            if reduction == "mean":
                current_vol = reshaped.mean(axis=(1, 3, 5))
            else:
                current_vol = reshaped.max(axis=(1, 3, 5))
            current_factor *= 2

        z_out = block.shape[0] // target_factor
        y_out = block.shape[1] // target_factor
        x_out = block.shape[2] // target_factor
        results[target_level] = current_vol[:z_out, :y_out, :x_out]

    return results
