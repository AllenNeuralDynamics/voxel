"""Sweep the write bench over a parameter grid -- one data load, one writer per (backend, slots).

    uv run -m bench.write.sweep [--batches N] [--samples N] [--keep]

Edit `SWEEP` below to choose what varies. The runner takes the cartesian product, orders points so the
*expensive* dims (those that force a writer/ring rebuild) change least often, loads the sample blocks once,
and records every point to the same results/write/<host>.jsonl (shared run_id) as single runs -- so they
pool in analysis. Concurrency caps are fixed for the whole sweep (set `VOXEL_*` env before running); to
sweep them, run the sweep once per setting.

Geometry constraint: `batch_z = batch_z_shards * shard_z_chunks * max_level.factor` must equal BATCH_SIZE
(128, the frames pushed per batch). The default geometry (L7 / 1 / 1) satisfies it. To sweep `max_level`
you must also set `shard_z_chunks`/`batch_z_shards` so the product stays 128 (e.g. L6 with shard_z_chunks=2);
a bad combination fails loudly in `build_wconfig`.
"""

import argparse
import contextlib
from itertools import product

from ome_zarr_writer import Compression, DownscaleType, OMEZarrWriter
from ome_zarr_writer.array import ArrayWriter

from bench.harness import Results, new_run_id
from bench.write.constants import PACKAGES, RESULTS_PATH
from bench.write.run import (
    _concurrency,
    _storage,
    build_wconfig,
    clear_artifacts,
    console,
    load_blocks,
    purge_target,
    run_combo,
)
from vxl.system import load_voxel_env

# Grid of what to vary. Values are the real types (enums, ints, floats). Cheap dims (target_shard_gb,
# compression, downscale, mode, fps) vary freely with no ring rebuild; the expensive ones below trigger one.
SWEEP = {
    "backend": [ArrayWriter.Backend.TS],
    "mode": ["local"],
    "slots": [4],
    "fps": [6.0, 8.0, 10.0, 12.0],
    "target_shard_gb": [0.5, 0.75, 1.0, 1.5, 2.0],
    "compression": [Compression.BLOSC_LZ4],
    "downscale": [DownscaleType.GAUSSIAN],
}

_GEOMETRY = ("max_level", "shard_z_chunks", "batch_z_shards", "target_shard_gb", "compression")  # -> WriterConfig
_EXPENSIVE = ("backend", "slots", "max_level", "shard_z_chunks", "batch_z_shards")  # force a writer/ring rebuild


def _points(grid: dict) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, combo, strict=True)) for combo in product(*(grid[k] for k in keys))]


def sweep(grid: dict, *, batches: int, samples: int, keep: bool) -> None:
    load_voxel_env()
    clear_artifacts("pre-run")
    blocks = load_blocks(samples)
    caps = _concurrency()
    run_id = new_run_id()
    results = Results(RESULTS_PATH, bench="write", run_id=run_id, packages=PACKAGES)

    points = _points(grid)
    points.sort(key=lambda p: tuple(str(p.get(k)) for k in _EXPENSIVE))  # minimize writer/ring rebuilds
    console.rule(f"[bold]write sweep[/]  run_id={run_id}  {len(points)} points  batches={batches} samples={samples}")

    writers: dict[tuple, OMEZarrWriter] = {}
    prev: tuple | None = None  # (mode, bn, tag) of the last point; safe to purge once the next begin_stack runs
    n = 0
    try:
        for i, p in enumerate(points):
            be, slots, bn = p["backend"], p["slots"], p["backend"].name.lower()
            writer = writers.get((be, slots))
            if writer is None:
                writer = writers[(be, slots)] = OMEZarrWriter(backend=be, slots=slots)
            geometry = {k: p[k] for k in _GEOMETRY if k in p}
            wconfig = build_wconfig(blocks, batches, p.get("downscale", DownscaleType.GAUSSIAN), **geometry)
            tag = f"p{i}"  # each point writes to its own target -- successive configs must not share a path
            label, storage = _storage(p["mode"], bn, tag=tag)
            try:
                run_combo(
                    writer,
                    wconfig,
                    storage,
                    blocks,
                    bn,
                    label,
                    results,
                    caps,
                    fps=p["fps"],
                    batches=batches,
                    samples=samples,
                    slots=slots,
                )
                n += 1
            except Exception as e:  # one point failing shouldn't abort the sweep
                console.print(f"[red]  point {p} FAILED {type(e).__name__}: {str(e).splitlines()[0][:120]}[/]")
                # A mid-stack failure leaves the writer's stack open; drop it (the close releases its target
                # handles too) so the next point starts fresh and the failure doesn't cascade.
                with contextlib.suppress(Exception):
                    writer.close()
                writers.pop((be, slots), None)
            # This point's begin_stack (ring rebind) or the failure close above released the *previous*
            # point's target -- safe to delete now, which bounds disk to ~2 points' worth.
            if prev is not None:
                purge_target(*prev)
            prev = (p["mode"], bn, tag)
    finally:
        for w in writers.values():
            try:
                w.close()  # releases the last point's target handles
            except Exception:  # a poisoned writer's close re-raises its failed batch; don't crash cleanup
                console.print("[dim]  (a writer failed to close cleanly)[/]")
        if prev is not None:
            purge_target(*prev)  # last point, now that its writer is closed
        if not keep:
            clear_artifacts("cleanup")  # backstop: clears any residue + VAST

    console.print(f"[dim]recorded {n}/{len(points)} points -> {RESULTS_PATH}[/]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="sweep the write bench over the SWEEP grid")
    ap.add_argument("--batches", type=int, default=20, help="batches per point (default 20; want rotation)")
    ap.add_argument("--samples", type=int, default=1, help="real-data samples loaded once (default 1)")
    ap.add_argument("--keep", action="store_true", help="keep artifacts after the sweep (default: clear)")
    args = ap.parse_args()
    sweep(SWEEP, batches=args.batches, samples=args.samples, keep=args.keep)
