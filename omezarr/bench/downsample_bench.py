"""Benchmark harness for the 3D mean-pyramid downsample kernel.

Compares the production kernel against two prototype variants to isolate where time goes on the
dominant L0→L1 pass, and verifies the prototypes produce numerically equivalent output:

    current  : ome_zarr_writer.buffer._pyramid.pyramids_3d_numba (parallel=True) — upcasts the whole
               L0 block to float32 up front, parallel prange over the output-Z dimension only.
    flat_f32 : same up-front float32 upcast, but the kernel's parallel loop is flattened over
               (T_out * H_out) — isolates the effect of (b) more parallelism.
    proto    : no up-front upcast (the first step reads the uint16 L0 directly; numba specializes the
               kernel on the input dtype), plus the flattened parallel loop — (b) + (c) together.

Run (defaults to a 128 x 4096 x 4096 uint16 block ≈ 4 GiB):

    uv run python omezarr/bench/downsample_bench.py [Z Y X] [--repeats N] [--level L7]

Threading layer and thread count are read from the environment (numba fixes them at import), so
compare layers by running the script under each:

    NUMBA_THREADING_LAYER=workqueue uv run python omezarr/bench/downsample_bench.py
    NUMBA_THREADING_LAYER=tbb       uv run python omezarr/bench/downsample_bench.py
    NUMBA_NUM_THREADS=64            uv run python omezarr/bench/downsample_bench.py

The reported numbers are wall time and effective throughput over the L0 input bytes; the prototypes'
max-abs-difference from `current` is printed per level (expected ~0, up to float32 rounding).
"""

import math
import os
import sys
import time
from collections.abc import Callable
from statistics import median

import numpy as np
from numba import get_num_threads, jit, prange, threading_layer

from ome_zarr_writer.buffer._pyramid import pyramids_3d_numba
from ome_zarr_writer.dataset import ScaleLevel


def _kernel_3d_mean_flat(vol: np.ndarray, out: np.ndarray) -> None:
    """2×2×2 box-average reduction with the parallel loop flattened over (T_out * H_out).

    numba parallelizes only the outermost `prange`; collapsing the two outer indices into one exposes
    ``T_out * H_out`` iterations instead of ``T_out``, so the dominant pass can use every core rather
    than being capped at the (small) output-Z extent. `vol` may be uint16 or float32 — numba compiles a
    separate specialization per input dtype, which is what lets the first step read the uint16 L0
    directly (no whole-block float32 copy).
    """
    T_out, H_out, W_out = out.shape
    for idx in prange(T_out * H_out):
        t = idx // H_out
        i = idx - t * H_out
        t2 = t * 2
        i2 = i * 2
        for j in range(W_out):
            j2 = j * 2
            s = 0.0
            for dt in range(2):
                for di in range(2):
                    for dj in range(2):
                        s += vol[t2 + dt, i2 + di, j2 + dj]
            out[t, i, j] = s * 0.125


_mean_flat: Callable[[np.ndarray, np.ndarray], None] = jit(
    nopython=True, parallel=True, fastmath=True, cache=True
)(_kernel_3d_mean_flat)


def pyramids_3d_flat(block: np.ndarray, max_level: ScaleLevel, *, upcast: bool) -> dict[ScaleLevel, np.ndarray]:
    """Cascaded mean pyramid using the flattened kernel.

    `upcast=True` materializes the L0 block as float32 up front (like the production path — isolates the
    flattening win). `upcast=False` leaves the L0 as uint16 and lets the first `_mean_flat` call
    specialize on uint16, so the ~2× float32 copy of the largest array is never made.
    """
    levels = sorted((lvl for lvl in max_level.levels if lvl != ScaleLevel.L0), key=lambda x: x.factor)
    current = block.astype(np.float32, copy=False) if upcast else block
    current_factor = 1
    results: dict[ScaleLevel, np.ndarray] = {}
    for target in levels:
        steps = int(math.log2(target.factor)) - int(math.log2(current_factor))
        for _ in range(steps):
            z, y, x = current.shape
            z2, y2, x2 = (z // 2) * 2, (y // 2) * 2, (x // 2) * 2
            if min(z2, y2, x2) == 0:
                break
            out = np.empty((z2 // 2, y2 // 2, x2 // 2), dtype=np.float32)
            _mean_flat(current[:z2, :y2, :x2], out)
            current = out
            current_factor *= 2
        z_out = block.shape[0] // target.factor
        y_out = block.shape[1] // target.factor
        x_out = block.shape[2] // target.factor
        results[target] = current[:z_out, :y_out, :x_out]
    return results


def _time(
    fn: Callable[[np.ndarray, ScaleLevel], dict[ScaleLevel, np.ndarray]],
    block: np.ndarray,
    max_level: ScaleLevel,
    repeats: int,
) -> tuple[float, dict[ScaleLevel, np.ndarray]]:
    result = fn(block, max_level)  # warm-up: triggers JIT compilation and first-touches the pages
    times: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn(block, max_level)
        times.append(time.perf_counter() - t0)
    return median(times), result


def _max_diff(a: dict[ScaleLevel, np.ndarray], b: dict[ScaleLevel, np.ndarray]) -> float:
    diff = 0.0
    for level in a:
        if level in b:
            diff = max(diff, float(np.max(np.abs(a[level].astype(np.float32) - b[level].astype(np.float32)))))
    return diff


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    z = int(args[0]) if len(args) > 0 else 128
    y = int(args[1]) if len(args) > 1 else 4096
    x = int(args[2]) if len(args) > 2 else 4096
    repeats = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--repeats=")), 3)
    level_name = next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--level=")), "L7")
    max_level = ScaleLevel[level_name]

    l0_gb = z * y * x * 2 / 1e9
    print(f"block=({z}, {y}, {x}) uint16  L0={l0_gb:.2f} GB  max_level={max_level.name}  repeats={repeats}")
    print(f"NUMBA_NUM_THREADS={get_num_threads()}  requested_layer={os.environ.get('NUMBA_THREADING_LAYER', '(default)')}")

    if "--random" in sys.argv:
        block = np.random.randint(0, 65536, size=(z, y, x), dtype=np.uint16)  # non-trivial correctness check
    else:
        block = np.zeros((z, y, x), dtype=np.uint16)

    variants: dict[str, Callable[[np.ndarray, ScaleLevel], dict[ScaleLevel, np.ndarray]]] = {
        "current ": lambda b, ml: pyramids_3d_numba(b, ml, parallel=True),
        "flat_f32": lambda b, ml: pyramids_3d_flat(b, ml, upcast=True),
        "proto   ": lambda b, ml: pyramids_3d_flat(b, ml, upcast=False),
    }

    baseline: dict[ScaleLevel, np.ndarray] | None = None
    for name, fn in variants.items():
        t, result = _time(fn, block, max_level, repeats)
        if baseline is None:
            baseline = result
        diff = _max_diff(result, baseline)
        print(f"  {name}: {t * 1000:8.1f} ms   {l0_gb / t:6.2f} GB/s   max_abs_diff_vs_current={diff:.3g}")

    print(f"active_threading_layer={threading_layer()}")


if __name__ == "__main__":
    main()
