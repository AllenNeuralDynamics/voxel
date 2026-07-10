"""Report which numba threading layer this machine selects, and probe each layer's availability + speed.

numba fixes its threading layer per-process (at the first parallel region), so to compare layers this
spawns one subprocess per layer with NUMBA_THREADING_LAYER set. The **default** row is what the writer's
flush worker actually uses (`_worker_init` sets THREADING_LAYER="default", priority tbb > omp > workqueue);
the others show which specific layers are installed/loadable here and how they compare on the real
pyramid kernel. `workqueue` is always available but slowest; `omp` needs an OpenMP runtime (usually
present on Windows/Linux); `tbb` needs a numba-loadable Intel TBB (often conda-only on Windows).

    uv run python bench/numba_threading_layer.py
"""

import os
import subprocess
import sys
import time

import numba
import numpy as np
from ome_zarr_writer.dataset import ScaleLevel
from ome_zarr_writer.pyramid import pyramids_3d_numba

LAYERS = ["default", "tbb", "omp", "workqueue"]
BLOCK = (64, 512, 512)  # representative L0 block for the timed pyramid
REPEATS = 5


def _probe_one() -> None:
    """Child mode: NUMBA_THREADING_LAYER is already set in the environment (numba reads it at import).
    Run the real pyramid kernel once (warm JIT + init the layer), time it, and print one result line."""
    blk = np.random.default_rng(0).integers(0, 4000, BLOCK, dtype=np.uint16)
    try:
        pyramids_3d_numba(blk, ScaleLevel.L3, parallel=True)  # warm JIT + select/init the layer
        t = time.perf_counter()
        for _ in range(REPEATS):
            pyramids_3d_numba(blk, ScaleLevel.L3, parallel=True)
        ms = (time.perf_counter() - t) / REPEATS * 1000
        print(f"OK   selected={numba.threading_layer():<10} threads={numba.get_num_threads():<4} {ms:6.1f} ms/call")
    except Exception as e:  # report any load/selection failure, don't crash the sweep
        print(f"UNAVAILABLE  ({type(e).__name__}: {str(e).splitlines()[0]})")


def main() -> None:
    if os.environ.get("_NUMBA_BENCH_CHILD"):
        _probe_one()
        return
    print(f"platform={sys.platform} | block={BLOCK} | probing numba threading layers (subprocess per layer)\n")
    for layer in LAYERS:
        env = {**os.environ, "NUMBA_THREADING_LAYER": layer, "_NUMBA_BENCH_CHILD": "1"}
        out = subprocess.run([sys.executable, __file__], env=env, capture_output=True, text=True, check=False)
        line = out.stdout.strip() or (out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "(no output)")
        print(f"  requested={layer:<10} -> {line}")
    print("\n'default' is what the writer's worker uses. tbb > omp > workqueue in priority; workqueue is the")
    print("always-available fallback (slowest). On Windows, tbb usually needs conda; omp loads for free.")


if __name__ == "__main__":
    main()
