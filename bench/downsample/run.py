"""Benchmark the production 3D pyramid downsample (`ome_zarr_writer.pyramid.pyramids_3d_numba`).

Measures the SHIPPED kernel -- no bench-local kernels -- sweeping numba's active thread count and the
reduction on one in-RAM block, recording GB/s vs threads (the process-stage scaling behind the write
bench's numba-thread findings). Results accumulate in results/downsample/<host>.jsonl; analyse with
`bench.downsample.analysis` / `loaders`.

    uv run -m bench.downsample.run [Z Y X] [--level=L7] [--reductions=gaussian,mean]
                                   [--threads=1,2,4,8,16,32,64] [--repeats=3]

Default block 128 x 2048 x 2048 uint16 (~1 GiB), generated once and reused across all points.
`NUMBA_NUM_THREADS` caps the pool; `--threads` above it are clamped. Set `NUMBA_THREADING_LAYER` to compare
layers (numba fixes it at import); the active layer is recorded per run.
"""

import argparse
import time
from statistics import median

import numba
import numpy as np
from ome_zarr_writer.dataset import DownscaleType, ScaleLevel
from ome_zarr_writer.pyramid import pyramids_3d_numba
from pydantic import BaseModel
from rich import box
from rich.console import Console
from rich.table import Table

from bench.downsample.constants import PACKAGES, RESULTS_PATH
from bench.harness import Results, new_run_id

console = Console()


class DownsampleRun(BaseModel):
    reduction: str  # gaussian / mean / max / min
    threads: int  # numba active threads (set_num_threads)
    pool_max: int  # NUMBA_NUM_THREADS (the thread-pool ceiling)
    threading_layer: str  # tbb / omp / workqueue -- what numba actually used
    block_z: int
    block_y: int
    block_x: int
    dtype: str
    max_level: str
    parallel: bool


class DownsampleResult(BaseModel):
    time_s: float  # median wall over repeats (throughput = l0_bytes / time_s)
    repeats: int
    times_s: list[float]  # raw per-repeat times


def _time(block: np.ndarray, max_level: ScaleLevel, reduction: DownscaleType, repeats: int) -> list[float]:
    pyramids_3d_numba(block, max_level, reduction=reduction, parallel=True)  # warm-up: JIT + first-touch pages
    out = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        pyramids_3d_numba(block, max_level, reduction=reduction, parallel=True)
        out.append(time.perf_counter() - t0)
    return out


def run(
    *,
    block_shape: tuple[int, int, int],
    max_level: ScaleLevel,
    reductions: tuple[DownscaleType, ...],
    threads: tuple[int, ...],
    repeats: int,
) -> None:
    pool_max = numba.get_num_threads()
    thread_counts = sorted({max(1, min(t, pool_max)) for t in threads})
    z, y, x = block_shape
    block = np.random.default_rng(0).integers(0, 4000, size=block_shape, dtype=np.uint16)  # real data in RAM
    l0_gb = block.nbytes / 1e9

    run_id = new_run_id()
    results = Results(RESULTS_PATH, bench="downsample", run_id=run_id, packages=PACKAGES)
    console.rule(f"[bold]downsample bench[/]  run_id={run_id}")
    console.print(
        f"block=({z},{y},{x}) uint16  L0={l0_gb:.2f} GB  max_level={max_level.name}  pool_max={pool_max}  "
        f"reductions={[r.name.lower() for r in reductions]}  threads={thread_counts}  repeats={repeats}"
    )

    layer = "?"
    table = Table(box=box.SIMPLE)
    for col in ("reduction", "threads", "ms", "GB/s"):
        table.add_column(col, justify="left" if col == "reduction" else "right")
    for reduction in reductions:
        for n in thread_counts:
            numba.set_num_threads(n)
            times = _time(block, max_level, reduction, repeats)
            layer = numba.threading_layer()  # valid only after a parallel region has run
            med = median(times)
            results.append(
                DownsampleRun(
                    reduction=reduction.name.lower(),
                    threads=n,
                    pool_max=pool_max,
                    threading_layer=layer,
                    block_z=z,
                    block_y=y,
                    block_x=x,
                    dtype="uint16",
                    max_level=max_level.name,
                    parallel=True,
                ),
                DownsampleResult(time_s=round(med, 4), repeats=repeats, times_s=[round(t, 4) for t in times]),
            )
            table.add_row(reduction.name.lower(), str(n), f"{med * 1000:.1f}", f"{l0_gb / med:.2f}")
    console.print(table)
    rows = len(reductions) * len(thread_counts)
    console.print(f"[dim]threading_layer={layer}  recorded {rows} rows -> {RESULTS_PATH}[/]")


def _parse_args() -> dict:
    p = argparse.ArgumentParser(description="benchmark the production pyramid downsample vs thread count")
    p.add_argument("dims", nargs="*", type=int, help="block Z Y X (default 128 2048 2048)")
    p.add_argument("--level", default="L7", help="max pyramid level (default L7)")
    p.add_argument("--reductions", default="gaussian,mean", help="comma list: gaussian,mean,max,min")
    p.add_argument("--threads", default="1,2,4,8,16,32,64", help="comma list of numba thread counts")
    p.add_argument("--repeats", type=int, default=3, help="timed repeats per point (median reported)")
    a = p.parse_args()

    if a.dims and len(a.dims) != 3:
        p.error("provide exactly 3 dims (Z Y X) or none")
    dims = tuple(a.dims) if len(a.dims) == 3 else (128, 2048, 2048)
    try:
        reductions = tuple(DownscaleType(r.strip()) for r in a.reductions.split(","))
    except ValueError as e:
        p.error(f"unknown reduction: {e}")
    try:
        max_level = ScaleLevel[a.level]
    except KeyError:
        p.error(f"unknown level {a.level!r}; use L0..L7")
    threads = tuple(int(t) for t in a.threads.split(","))
    return {
        "block_shape": dims,
        "max_level": max_level,
        "reductions": reductions,
        "threads": threads,
        "repeats": a.repeats,
    }


if __name__ == "__main__":
    run(**_parse_args())
