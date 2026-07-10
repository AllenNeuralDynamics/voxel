"""Multi-scale pyramid generation for the buffer package.

Two backends, same result up to floating-point rounding:

- `pyramids_3d_numba`: JIT-compiled kernels, parameterized by `reduction`
  (a `DownscaleType`: MEAN/MAX/MIN/GAUSSIAN) and `parallel` (whether the kernel
  uses numba's prange thread pool). Primary path in production.
- `pyramids_3d_numpy`: pure-numpy reductions. Kept as a reference implementation
  and fallback when numba is unavailable.

For the numba path the kernel bodies are written once per reduction and
JIT-specialized twice (serial + parallel) at module import. `prange` on the
outermost loop degenerates to `range` under `@jit(parallel=False)`, so a single
source supports both variants without duplication.

`mean`/`max`/`min` reduce each 2×2×2 block independently, in one `(vol, out)` kernel.
`gaussian` is a genuine anti-aliasing downscale — the rest of this docstring is how it works.

How the gaussian math works
---------------------------
A *tap* is one filter coefficient — a point where the filter reads an input sample. The filter
[1,3,3,1] has 4 taps: each output is `1·a + 3·b + 3·c + 1·d` over 4 input samples. Those weights
are a row of Pascal's triangle (the *binomial* coefficients), and [1,3,3,1] = [1,1]⊛[1,1]⊛[1,1] —
the 2-box average convolved with itself three times. Repeated averaging tends to a Gaussian (CLT),
so a binomial filter is a cheap integer approximation of a Gaussian low-pass. That low-pass is the
whole point: decimation (dropping every other sample) folds frequencies above the new Nyquist back
in as aliasing; blurring first removes them. `mean` is a 2-tap box [1,1]/2 — a crude low-pass that
leaks high frequencies, so it aliases more.

One 2× step, in 1-D: for output `i`, centre the 4 taps on the 2-block `(2i, 2i+1)`, reading indices
{2i-1, 2i, 2i+1, 2i+2} (edge-clamped), weights (1,3,3,1), then divide by 8. Worked example on
`v = [10,12,40,42,44,46,12,10]`:

    out[1]: idx {1,2,3,4}          → (1·12 + 3·40 + 3·42 + 1·44) / 8 = 302/8 = 37.75
    out[3]: idx {5,6,7,8}→{5,6,7,7}→ (1·46 + 3·12 + 3·10 + 1·10) / 8 = 122/8 = 15.25   (8 clamped to 7)

The weights sum to 8, so ÷8 makes it a weighted average — a constant field stays constant (DC gain 1).
The taps are symmetric about `2i+0.5`, the midpoint of the block `mean` averages, so `gaussian` and
`mean` land on the *same* output grid (no half-pixel shift; the classic 5-tap [1,4,6,4,1] centres on
`2i` and would shift). Chaining the step across levels widens the effective Gaussian, exactly as a
Burt–Adelson pyramid does.

3-D via separability: the 3-D kernel is the outer product `w[dz]·w[dy]·w[dx]` (4×4×4 = 64 weights),
but because it factors, applying the 1-D filter along X then Y then Z gives the identical result for
only 4+4+4 = 12 taps/voxel instead of 64. `_binom_x`/`_binom_y` do the X/Y passes (sums only, ÷8
deferred); `_binom_z` combines the four planes and applies the single ÷512 (= ÷8³) that normalises
all three passes at once.

Cost & memory: the fused 64-tap form was measured ~5.4× `mean` (strided gathers thrash cache) and
became the pipeline's binding stage, missing capture rate. Separable is 12 taps/voxel but its 1-D
passes are contiguous and SIMD-friendly, so measured wall-time is *on par with* `mean` (even a touch
faster). To get that speed *without* separability's usual full-size float32 intermediate (~half of L0
as f32, materialised per active worker — unsafe next to the ring), `_gaussian_downscale` streams by
Z-plane: each input plane is X/Y-reduced exactly once into a small rolling cache (≈4–5 planes) and the
Z pass combines cached planes. Peak scratch is ~1 GB per worker regardless of Z or slot count, and no
input plane is reduced twice.

`BatchSlot`'s worker is the only caller and passes `parallel=True` (a single Python
caller per worker process). The serial (`parallel=False`) variant remains JIT-specialized
so the source stays valid for any in-process caller and for tests.
"""

import math
from collections.abc import Callable

import numpy as np
from numba import jit, prange

from ome_zarr_writer.dataset import DownscaleType, ScaleLevel


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


def _kernel_3d_min(vol: np.ndarray, out: np.ndarray) -> None:
    """2×2×2 min-projection reduction: out[t, i, j] = min of the 8 covering voxels."""
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
                            if v < m:
                                m = v
                out[t, i, j] = m


# --- gaussian: three separable 1-D binomial [1,3,3,1] decimate-by-2 passes ---
# Each pass reads 4 clamped taps per output element. X and Y run on a single (Y,X) input plane; Z
# combines four already-X/Y-reduced planes. The /8 per pass is folded into the final /512 in the Z
# pass, so X and Y leave their sums un-normalised (values grow ≤64×; exact in float32).


def _binom_x(plane: np.ndarray, out: np.ndarray) -> None:
    """X pass: (Y, X) input plane → (Y, Xo) with X decimated by 2. Sum only (no /8)."""
    Y, X = plane.shape
    Xo = out.shape[1]
    for y in prange(Y):
        for xo in range(Xo):
            c = xo * 2
            x0 = max(c - 1, 0)
            x2 = min(c + 1, X - 1)
            x3 = min(c + 2, X - 1)
            out[y, xo] = plane[y, x0] + 3.0 * plane[y, c] + 3.0 * plane[y, x2] + plane[y, x3]


def _binom_y(tmp: np.ndarray, out: np.ndarray) -> None:
    """Y pass: (Y, Xo) X-reduced plane → (Yo, Xo) with Y decimated by 2. Sum only (no /8)."""
    Y, Xo = tmp.shape
    Yo = out.shape[0]
    for yo in prange(Yo):
        c = yo * 2
        y0 = max(c - 1, 0)
        y2 = min(c + 1, Y - 1)
        y3 = min(c + 2, Y - 1)
        for xo in range(Xo):
            out[yo, xo] = tmp[y0, xo] + 3.0 * tmp[c, xo] + 3.0 * tmp[y2, xo] + tmp[y3, xo]


def _binom_z(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, p3: np.ndarray, out: np.ndarray) -> None:
    """Z pass: combine four X/Y-reduced planes (weights 1,3,3,1) into one output plane, applying the
    single /512 that normalises all three separable passes at once."""
    Yo, Xo = out.shape
    for yo in prange(Yo):
        for xo in range(Xo):
            out[yo, xo] = (p0[yo, xo] + 3.0 * p1[yo, xo] + 3.0 * p2[yo, xo] + p3[yo, xo]) * (1.0 / 512.0)


# ---------------------------------------------------------------------------
# JIT specialization — each kernel is compiled twice, once serial, once
# parallel. Compilation is lazy (first call per signature) and cached on disk.
# ---------------------------------------------------------------------------

_jit_serial = jit(nopython=True, parallel=False, fastmath=True, cache=True)
_jit_parallel = jit(nopython=True, parallel=True, fastmath=True, cache=True)

# Block reductions: one (vol, out) kernel each, keyed by (reduction, parallel).
_KERNELS: dict[tuple[DownscaleType, bool], Callable[[np.ndarray, np.ndarray], None]] = {
    (DownscaleType.MEAN, False): _jit_serial(_kernel_3d_mean),
    (DownscaleType.MEAN, True): _jit_parallel(_kernel_3d_mean),
    (DownscaleType.MAX, False): _jit_serial(_kernel_3d_max),
    (DownscaleType.MAX, True): _jit_parallel(_kernel_3d_max),
    (DownscaleType.MIN, False): _jit_serial(_kernel_3d_min),
    (DownscaleType.MIN, True): _jit_parallel(_kernel_3d_min),
}

# Gaussian is separable, so it has three passes instead of one kernel; the orchestrator below drives
# them. Specialized serial + parallel like the block kernels (annotated so the jit wrappers' call
# signatures are visible to the type checker, as _KERNELS is).
_Pass1 = Callable[[np.ndarray, np.ndarray], None]
_GAUSS_X: dict[bool, _Pass1] = {False: _jit_serial(_binom_x), True: _jit_parallel(_binom_x)}
_GAUSS_Y: dict[bool, _Pass1] = {False: _jit_serial(_binom_y), True: _jit_parallel(_binom_y)}
_GAUSS_Z: dict[bool, Callable[[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray], None]] = {
    False: _jit_serial(_binom_z),
    True: _jit_parallel(_binom_z),
}

# Every reduction the step dispatcher handles. The test suite asserts this equals set(DownscaleType),
# so a new metadata value can't be declared without a kernel behind it (the anti-"metadata lie" guard).
_SUPPORTED_REDUCTIONS = frozenset({DownscaleType.MEAN, DownscaleType.MAX, DownscaleType.MIN, DownscaleType.GAUSSIAN})


def _gaussian_downscale(vol: np.ndarray, out: np.ndarray, parallel: bool) -> None:
    """Separable binomial 2× downscale of `vol` (Z, Y, X) into `out` (Zo, Yo, Xo), streamed by Z-plane.

    Each input plane is X- then Y-reduced exactly once into a small rolling cache; the Z pass combines
    the four cached planes an output plane needs (indices 2zo-1..2zo+2, edge-clamped). Peak scratch is
    the cache (≈4–5 planes of shape (Yo, Xo)) plus one (Y, Xo) X-pass buffer — ~1 GB for a 151 MP frame,
    independent of Z and of how many workers run concurrently.
    """
    binom_x, binom_y, binom_z = _GAUSS_X[parallel], _GAUSS_Y[parallel], _GAUSS_Z[parallel]
    z_in, y_in, x_in = vol.shape
    z_out, y_out, x_out = out.shape
    x_buf = np.empty((y_in, x_out), dtype=np.float32)  # reused scratch for the X pass of one plane
    cache: dict[int, np.ndarray] = {}  # global input z → its X/Y-reduced (Yo, Xo) plane (un-normalised)

    def reduced(zg: int) -> np.ndarray:
        zg = min(max(zg, 0), z_in - 1)  # clamp (replicate edge)
        plane = cache.get(zg)
        if plane is None:
            binom_x(vol[zg], x_buf)
            plane = np.empty((y_out, x_out), dtype=np.float32)
            binom_y(x_buf, plane)
            cache[zg] = plane
        return plane

    for zo in range(z_out):
        c = zo * 2
        p0, p1, p2, p3 = reduced(c - 1), reduced(c), reduced(c + 1), reduced(c + 2)
        binom_z(p0, p1, p2, p3, out[zo])
        lo = max(c - 1, 0)  # planes below the next window's first tap are done — drop them
        for done in [k for k in cache if k < lo]:
            del cache[done]


# ---------------------------------------------------------------------------
# Orchestration — one implementation, parameterized by reduction and whether
# the inner kernel should parallelize across threads.
# ---------------------------------------------------------------------------


def pyramids_3d_numba(
    block: np.ndarray,
    max_level: ScaleLevel,
    reduction: DownscaleType = DownscaleType.MEAN,
    parallel: bool = False,
) -> dict[ScaleLevel, np.ndarray]:
    """Compute a 3D multi-scale pyramid via chained 2×2×2 reductions.

    Args:
        block: L0 input volume with shape (Z, Y, X). Any numeric dtype — internally
            upcast to float32 for the reduction.
        max_level: Highest pyramid level to compute. All levels L1..max_level are
            produced; L0 is not included in the returned dict (it's the input).
        reduction: DownscaleType — MEAN box-average, MAX/MIN projection, or GAUSSIAN
            anti-aliased (separable binomial prefilter, decimate by 2).
        parallel: If True, the inner kernel uses numba's prange thread pool. Safe
            only when there is a single Python caller (e.g., inside a worker
            process). Must be False when multiple Python threads may call
            concurrently.

    Returns:
        Mapping of each non-L0 level to its reduced float32 volume.
    """
    if reduction not in _SUPPORTED_REDUCTIONS:
        raise ValueError(f"Unsupported downscale type: {reduction}")

    results: dict[ScaleLevel, np.ndarray] = {}
    levels = [level for level in max_level.levels if level != ScaleLevel.L0]
    sorted_levels = sorted(levels, key=lambda x: x.factor)

    current_factor = 1
    # Read L0 in its native dtype. The kernel accumulates in float64 and integer pixel values are exact
    # in float32/float64, so an up-front full float32 copy of the (largest) L0 array is wasted work —
    # it was the dominant downsample cost. numba specializes the kernel on the input dtype and writes
    # float32 for L1; every subsequent level is already float32.
    current_vol = block

    for target_level in sorted_levels:
        target_factor = target_level.factor
        steps_needed = int(math.log2(target_factor)) - int(math.log2(current_factor))

        for _ in range(steps_needed):
            z, y, x = current_vol.shape
            z2, y2, x2 = (z // 2) * 2, (y // 2) * 2, (x // 2) * 2
            if min(z2, y2, x2) == 0:
                break
            out = np.empty((z2 // 2, y2 // 2, x2 // 2), dtype=np.float32)
            vol = current_vol[:z2, :y2, :x2]
            if reduction == DownscaleType.GAUSSIAN:
                _gaussian_downscale(vol, out, parallel)
            else:
                _KERNELS[(reduction, parallel)](vol, out)
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


def _binomial_decimate_axis(v: np.ndarray, axis: int) -> np.ndarray:
    """One separable binomial [1,3,3,1]/8 pass with stride-2 decimation along `axis`, edge-clamped —
    the numpy mirror of `_kernel_3d_gaussian`'s per-axis taps (same clamp and weights)."""
    n = v.shape[axis]
    no = n // 2
    c = 2 * np.arange(no)
    t0 = np.take(v, np.clip(c - 1, 0, n - 1), axis=axis)
    t1 = np.take(v, c, axis=axis)
    t2 = np.take(v, np.clip(c + 1, 0, n - 1), axis=axis)
    t3 = np.take(v, np.clip(c + 2, 0, n - 1), axis=axis)
    return ((t0 + 3.0 * t1 + 3.0 * t2 + t3) * 0.125).astype(np.float32, copy=False)


def pyramids_3d_numpy(
    block: np.ndarray,
    max_level: ScaleLevel,
    reduction: DownscaleType = DownscaleType.MEAN,
) -> dict[ScaleLevel, np.ndarray]:
    """Compute a 3D multi-scale pyramid using pure numpy reductions.

    Same semantics as `pyramids_3d_numba`. `mean`/`max`/`min` use `reshape` plus the
    matching `ndarray` reduction; `gaussian` uses a separable binomial decimate
    (`_binomial_decimate_axis`) so it stays bit-comparable (up to fp rounding) with the
    numba kernel. No `parallel` parameter because numpy has no equivalent knob — internal
    parallelism depends on the linked BLAS/LAPACK and is not user-controllable here.

    Args:
        block: L0 input volume with shape (Z, Y, X). Any numeric dtype — internally
            upcast to float32 for the reduction.
        max_level: Highest pyramid level to compute. All levels L1..max_level are
            produced; L0 is not included in the returned dict (it's the input).
        reduction: DownscaleType — MEAN box-average, MAX/MIN projection, or GAUSSIAN anti-aliased.

    Returns:
        Mapping of each non-L0 level to its reduced float32 volume.
    """
    results: dict[ScaleLevel, np.ndarray] = {}
    levels = [level for level in max_level.levels if level != ScaleLevel.L0]
    sorted_levels = sorted(levels, key=lambda x: x.factor)

    current_factor = 1
    # Read L0 in its native dtype; the reductions below force float32 output, so the result is
    # unchanged while avoiding an up-front full float32 copy of the largest array.
    current_vol = block

    for target_level in sorted_levels:
        target_factor = target_level.factor
        steps_needed = int(math.log2(target_factor)) - int(math.log2(current_factor))

        for _ in range(steps_needed):
            z, y, x = current_vol.shape
            z2, y2, x2 = (z // 2) * 2, (y // 2) * 2, (x // 2) * 2
            if min(z2, y2, x2) == 0:
                break
            if reduction == DownscaleType.GAUSSIAN:
                v = current_vol[:z2, :y2, :x2].astype(np.float32, copy=False)
                for axis in (0, 1, 2):  # separable [1,3,3,1]/8 decimate; order is irrelevant up to fp rounding
                    v = _binomial_decimate_axis(v, axis)
                current_vol = v
            else:
                reshaped = current_vol[:z2, :y2, :x2].reshape(z2 // 2, 2, y2 // 2, 2, x2 // 2, 2)
                if reduction == DownscaleType.MEAN:
                    current_vol = reshaped.mean(axis=(1, 3, 5), dtype=np.float32)
                elif reduction == DownscaleType.MIN:
                    current_vol = reshaped.min(axis=(1, 3, 5)).astype(np.float32, copy=False)
                else:
                    current_vol = reshaped.max(axis=(1, 3, 5)).astype(np.float32, copy=False)
            current_factor *= 2

        z_out = block.shape[0] // target_factor
        y_out = block.shape[1] // target_factor
        x_out = block.shape[2] // target_factor
        results[target_level] = current_vol[:z_out, :y_out, :x_out]

    return results
