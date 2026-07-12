"""Bench: write REAL frames through the actual `OMEZarrWriter` to Local / DirectS3 / StagedS3.

Reads a few real exaSPIM blocks (`bench.data.CATALOG`), then writes back-to-back batches through the
writer, pacing the add loop at a target fps so collect/flush overlap like a live acquisition. Per backend x
mode combo it records one raw measurement to `results/write/<host>.jsonl` (via `bench.harness.Results`) and
prints a rich summary: wall time, effective fps, stored bytes, and the per-batch pipeline timeline.

    uv run -m bench.write.run [--fps N] [--backends ts,zarrs] [--modes local,direct,staged]
                              [--slots N] [--batches N] [--samples N] [--downscale ...] [--keep]

Batches rotate through the loaded blocks (batch b uses block b % len) so successive batches are distinct
real data. `--batches > --slots` forces ring rotation, so a slow flush shows up as effective fps dropping
below target. Concurrency caps read from the environment (`VOXEL_NUMBA_THREADS`, `VOXEL_TS_CONCURRENCY`,
`VOXEL_ZARRS_SHARD_WORKERS`) are recorded with each run. Writes to a local temp dir + VAST scratch, cleaned
before and after (unless `--keep`). Needs VAST creds from ~/.voxel/.env via `vxl.system.load_voxel_env`.

`bench.write.sweep` reuses the functions here to sweep a parameter grid; analyse with `bench.write.report`.
"""

import argparse
import contextlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from cloudpathlib import S3Path
from ome_zarr_writer import (
    DirectS3,
    DownscaleType,
    Local,
    OMEZarrWriter,
    StagedS3,
    Storage,
    UIVec3D,
    UVec3D,
    WriterConfig,
)
from ome_zarr_writer.array import ArrayWriter
from pydantic import BaseModel
from rich import box
from rich.console import Console
from rich.table import Table

from bench.data import BATCH_SIZE, CATALOG, load_real_block
from bench.harness import Results, new_run_id
from bench.write.constants import (
    LOCAL_ROOT,
    PACKAGES,
    RESULTS_PATH,
    S3_BUCKET,
    S3_PREFIX,
    S3_ROOT,
    SCRATCH,
    VAST,
)
from vxl.system import load_voxel_env

MODE_KEYS = ("local", "direct", "staged")
BACKEND_KEYS = {"ts": ArrayWriter.Backend.TS, "zarrs": ArrayWriter.Backend.ZARRS}
_STAGES = ("collecting", "processing", "flushing", "transferring")

console = Console()


# ---------------------------------------------------------------------------
# Schemas: independent variables (`WriteRun`) and raw measurements (`WriteResult`) recorded per combo.
# Raw only -- fps / MB/s / ratio / drain_tail are derived in analysis, never stored (see bench/README.md).
# ---------------------------------------------------------------------------


class WriteRun(BaseModel):
    backend: str
    mode: str
    fps_target: float
    slots: int
    batches: int
    samples: int
    # output geometry / codec
    downscale: str
    compression: str
    max_level: str
    target_shard_gb: float
    shard_z_chunks: int
    batch_z_shards: int
    batch_z: int
    frame_y: int
    frame_x: int
    dtype: str
    # concurrency caps (env)
    numba_threads: int
    ts_concurrency: int
    zarrs_shard_workers: int


class BatchTiming(BaseModel):
    """One batch's stage offsets in seconds from the run's first collect start; [start, end] per stage,
    [null, null] for a stage that did not run (transfer only runs for StagedS3)."""

    batch: int
    collect: tuple[float | None, float | None]
    process: tuple[float | None, float | None]
    flush: tuple[float | None, float | None]
    transfer: tuple[float | None, float | None]


class WriteResult(BaseModel):
    collect_s: float  # wall time of the paced add loop
    wall_s: float  # add loop + end_stack drain
    stored_bytes: int  # compressed bytes actually on the store
    raw_bytes: int  # uncompressed bytes the codec ingested (writer's flushed_bytes)
    batches: list[BatchTiming]


@dataclass(frozen=True)
class BenchConfig:
    """One invocation's parameters (parsed from the CLI), passed explicitly rather than via globals."""

    fps: float
    slots: int
    batches: int
    samples: int
    downscale: DownscaleType
    backends: tuple[ArrayWriter.Backend, ...]
    modes: tuple[str, ...]
    keep: bool


# ---------------------------------------------------------------------------
# Storage + S3 helpers
# ---------------------------------------------------------------------------


def _storage(mode: str, bn: str, tag: str = "") -> tuple[str, Storage]:
    """Storage sink for a mode, namespaced by backend (and `tag` for a sweep point, so successive configs
    write to *distinct* paths instead of corrupting a shared one). The returned label is the plain mode."""
    sub = mode if not tag else f"{mode}-{tag}"
    if mode == "local":
        return "Local", Local(target=LOCAL_ROOT / bn / sub)
    if mode == "direct":
        return "DirectS3", DirectS3(target=S3Path(f"{S3_ROOT}/{bn}/{sub}"), store=VAST)
    if mode == "staged":
        return "StagedS3", StagedS3(scratch=SCRATCH / bn / sub, target=S3Path(f"{S3_ROOT}/{bn}/{sub}"), store=VAST)
    raise ValueError(f"unknown mode {mode!r}")


def _s3() -> BaseClient:
    return boto3.client(
        "s3", endpoint_url=VAST.endpoint, config=Config(region_name=VAST.region, s3={"addressing_style": "path"})
    )


def _concurrency() -> dict[str, int]:
    """The concurrency caps the writer processes will read from the environment (recorded per run)."""
    return {
        "numba_threads": int(os.environ.get("VOXEL_NUMBA_THREADS", "16")),
        "ts_concurrency": int(os.environ.get("VOXEL_TS_CONCURRENCY", "16")),
        "zarrs_shard_workers": int(os.environ.get("VOXEL_ZARRS_SHARD_WORKERS", "16")),
    }


def stored_bytes(target: Path | S3Path | None) -> int:
    """Compressed bytes on the store: sum local file sizes, or S3 object sizes under `target`."""
    if target is None:
        return 0
    if isinstance(target, S3Path):
        total = 0
        for page in (
            _s3().get_paginator("list_objects_v2").paginate(Bucket=target.bucket, Prefix=target.key.rstrip("/") + "/")
        ):
            total += sum(o["Size"] for o in page.get("Contents", []))
        return total
    return sum(f.stat().st_size for f in Path(target).rglob("*") if f.is_file())


def read_metrics(target: Path | S3Path) -> dict:
    """Load the writer's metrics.json from the dataset (S3 object or local file)."""
    if isinstance(target, S3Path):
        body = _s3().get_object(Bucket=target.bucket, Key=target.key.rstrip("/") + "/metrics.json")["Body"].read()
        return json.loads(body)
    return json.loads((Path(target) / "metrics.json").read_text())


def _parse_batches(metrics: dict) -> tuple[list[BatchTiming], int]:
    """Convert the writer's metrics.json into per-batch stage offsets (seconds from the first collect
    start) and the total raw bytes ingested. cleanup() deletes metrics.json, so this captures the only
    surviving copy of the per-batch timeline for later analysis."""
    batches = [b for b in metrics["batches"] if b["collecting"]["started"]]
    if not batches:
        return [], 0
    stamps = [
        datetime.fromisoformat(b[s][e]) for b in batches for s in _STAGES for e in ("started", "ended") if b[s][e]
    ]
    t0 = min(stamps)

    def off(ts: str | None) -> float | None:
        return round((datetime.fromisoformat(ts) - t0).total_seconds(), 2) if ts else None

    def pair(b: dict, stage: str) -> tuple[float | None, float | None]:
        return off(b[stage]["started"]), off(b[stage]["ended"])

    timings = [
        BatchTiming(
            batch=b["batch_idx"],
            collect=pair(b, "collecting"),
            process=pair(b, "processing"),
            flush=pair(b, "flushing"),
            transfer=pair(b, "transferring"),
        )
        for b in batches
    ]
    raw = sum(b["flushed_bytes"] for b in batches)
    return timings, raw


# ---------------------------------------------------------------------------
# Rendering (rich). Display may show derived values; the recorded JSONL never does.
# ---------------------------------------------------------------------------


def _fmt(stage: tuple[float | None, float | None]) -> str:
    a, b = stage
    return f"{a:6.1f}→{b:6.1f}" if a is not None and b is not None else "     -"


def _batch_table(result: WriteResult) -> Table:
    has_x = any(t.transfer[0] is not None for t in result.batches)
    table = Table(box=box.SIMPLE, pad_edge=False, show_edge=False, header_style="dim")
    table.add_column("b", justify="right", style="dim")
    for name in ("collect", "process", "flush"):
        table.add_column(name, justify="right")
    if has_x:
        table.add_column("transfer", justify="right")
    for t in result.batches:
        row = [str(t.batch), _fmt(t.collect), _fmt(t.process), _fmt(t.flush)]
        if has_x:
            row.append(_fmt(t.transfer))
        table.add_row(*row)
    return table


def _derived(batches: int, r: WriteResult) -> dict[str, float]:
    frames = BATCH_SIZE * batches
    ends = [t.flush[1] for t in r.batches if t.flush[1] is not None]
    collect_ends = [t.collect[1] for t in r.batches if t.collect[1] is not None]
    span = max(ends) if ends else r.wall_s
    drain_tail = span - max(collect_ends) if collect_ends else 0.0
    return {
        "eff_fps": frames / r.collect_s if r.collect_s else 0.0,
        "mb_s": r.stored_bytes / 1e6 / r.wall_s if r.wall_s else 0.0,
        "ratio": r.raw_bytes / r.stored_bytes if r.stored_bytes else float("nan"),
        "drain_tail": drain_tail,
    }


def _batch_summary(r: WriteResult) -> str:
    """Mean per-stage duration + a flush-growth callout -- the drain-falling-behind signal, so you don't
    have to eyeball 20 rows for it."""

    def durs(stage: str) -> list[float]:
        return [e - s for t in r.batches for s, e in [getattr(t, stage)] if s is not None and e is not None]

    parts = [f"{name} {sum(d) / len(d):.1f}s" for name in ("collect", "process", "flush") if (d := durs(name))]
    line = "  [dim]" + " · ".join(parts) + "[/]"
    flush = durs("flush")
    if len(flush) >= 3 and flush[0] and flush[-1] / flush[0] > 1.3:  # >30% growth = drain falling behind
        line += f"  [yellow]flush grew {flush[0]:.1f}->{flush[-1]:.1f}s ({flush[-1] / flush[0]:.1f}x)[/]"
    return line


def _print_combo(run: WriteRun, result: WriteResult) -> None:
    """Config line (the independent variables -- so each sweep point is self-describing), then the result
    line, then the per-batch timeline table and its summary."""
    d = _derived(run.batches, result)
    console.print(
        f"\n[bold cyan]{run.backend}/{run.mode}[/]  {run.compression} · shard {run.target_shard_gb}GB · "
        f"{run.max_level} · {run.downscale} · slots {run.slots} · batch_z {run.batch_z} · "
        f"{run.frame_y}x{run.frame_x} {run.dtype} · "
        f"caps {run.numba_threads}/{run.ts_concurrency}/{run.zarrs_shard_workers}"
    )
    console.print(
        f"  wall [b]{result.wall_s:.1f}s[/] · collect {result.collect_s:.1f}s "
        f"([b]{d['eff_fps']:.1f}[/]/{run.fps_target:.0f} fps) · store {result.stored_bytes / 1e9:.1f}GB "
        f"@ [b]{d['mb_s']:.0f} MB/s[/] · drain {d['drain_tail']:.1f}s · ratio {d['ratio']:.1f}x"
    )
    if result.batches:
        console.print(_batch_table(result))
        console.print(_batch_summary(result))


def _print_header(cfg: BenchConfig, wconfig: WriterConfig, blocks: list, run_id: str, caps: dict[str, int]) -> None:
    y, x = int(wconfig.volume_shape.y), int(wconfig.volume_shape.x)
    gb = sum(b.nbytes for b in blocks) / 1e9
    console.rule(f"[bold]write bench[/]  run_id={run_id}")
    console.print(
        f"frame={y}x{x} | batch_z={wconfig.batch_z} x {cfg.batches} batches = {BATCH_SIZE * cfg.batches} frames "
        f"@ {cfg.fps:.0f}fps | slots={cfg.slots} | {wconfig.compression} | downscale={wconfig.downscale_type} | "
        f"samples={len(blocks)} ({gb:.0f}GB)"
    )
    console.print(
        f"[dim]backends={[b.name.lower() for b in cfg.backends]} modes={list(cfg.modes)} "
        f"caps(numba={caps['numba_threads']}, ts={caps['ts_concurrency']}, zarrs={caps['zarrs_shard_workers']})[/]"
    )
    if cfg.slots >= cfg.batches:
        console.print(
            f"[yellow]note[/]: slots {cfg.slots} >= batches {cfg.batches}: ring won't rotate; raise --batches"
        )


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def clear_artifacts(label: str) -> None:
    """Remove every bench artifact -- local store, local scratch, and VAST objects under the bench prefix
    -- and *report* anything that survives rather than hiding it: locked local files (Windows, if a writer
    handle is still open) and VAST per-object delete errors or residue (verified by re-listing). Called both
    before a run (self-healing any prior killed run's leftovers, since cleanup otherwise only runs on a clean
    finish) and after (unless --keep). VAST failures are caught so an endpoint outage can't abort the bench."""
    for p in (LOCAL_ROOT, SCRATCH):
        shutil.rmtree(p, ignore_errors=True)
        if p.exists():
            console.print(f"  [yellow]{label}: WARNING {p} not fully removed (a file handle may still be open)[/]")
    try:
        s3 = _s3()
        errors = 0
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX + "/"):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                errors += len(s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": objs}).get("Errors", []))
        remaining = sum(
            len(pg.get("Contents", []))
            for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX + "/")
        )
        note = "cleared" if not (errors or remaining) else f"{errors} delete-errors, {remaining} objects STILL PRESENT"
        console.print(f"[dim]{label}: local + VAST {note}[/]")
    except Exception as e:
        console.print(
            f"[dim]{label}: local cleared; VAST cleanup FAILED ({type(e).__name__}: {str(e).splitlines()[0][:80]})[/]"
        )


def purge_target(mode: str, bn: str, tag: str = "") -> None:
    """Delete one sweep point's written data (local dataset, staged scratch, S3 prefix) so successive
    points don't accumulate on disk. Only call it once the point's writer has released the target -- i.e.
    after the *next* point's begin_stack rebinds the ring, or after the writer's close. Best-effort; the
    sweep's final clear_artifacts backstops anything left."""
    sub = mode if not tag else f"{mode}-{tag}"
    shutil.rmtree(LOCAL_ROOT / bn / f"{sub}.ome.zarr", ignore_errors=True)  # local dataset (writer adds .ome.zarr)
    shutil.rmtree(SCRATCH / bn / sub, ignore_errors=True)  # staged scratch
    if mode in ("direct", "staged"):
        prefix = f"{S3_PREFIX}/{bn}/{sub}"
        with contextlib.suppress(Exception):  # best-effort per-point purge; final cleanup covers residue
            s3 = _s3()
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=S3_BUCKET, Prefix=prefix):
                objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                if objs:
                    s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": objs})


# ---------------------------------------------------------------------------
# Run one combo (reused by the sweep)
# ---------------------------------------------------------------------------


def run_combo(
    writer: OMEZarrWriter,
    wconfig: WriterConfig,
    storage: Storage,
    blocks: list,
    backend: str,
    mode: str,
    results: Results,
    caps: dict[str, int],
    *,
    fps: float,
    batches: int,
    samples: int,
    slots: int,
) -> WriteResult:
    """Write `batches` batches through `writer` at `fps`, measure, record a JSONL row, print. All the
    varying inputs are explicit args so the sweep can drive it without a BenchConfig."""
    dw = writer.begin_stack(wconfig, storage)  # DatasetWriter; its .target + metrics.json survive end_stack
    interval = 1.0 / fps
    t0 = next_t = time.perf_counter()
    for batch_idx in range(batches):
        block = blocks[batch_idx % len(blocks)]  # rotate through the distinct real-data samples
        for i in range(BATCH_SIZE):
            writer.add_frame(block[i])
            next_t += interval  # pace at fps; if the writer back-pressures, add_frame runs long and we fall behind
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
    t_add = time.perf_counter()
    writer.end_stack()
    t_end = time.perf_counter()

    stored = stored_bytes(dw.target)
    timings, raw = [], 0
    try:
        timings, raw = _parse_batches(read_metrics(dw.target))
    except Exception as e:  # metrics are best-effort; still record wall/collect/stored
        console.print(f"  [yellow](metrics.json unavailable: {type(e).__name__}: {e})[/]")
    result = WriteResult(
        collect_s=round(t_add - t0, 2), wall_s=round(t_end - t0, 2), stored_bytes=stored, raw_bytes=raw, batches=timings
    )
    run = WriteRun(
        backend=backend,
        mode=mode,
        fps_target=fps,
        slots=slots,
        batches=batches,
        samples=samples,
        downscale=str(wconfig.downscale_type),
        compression=str(wconfig.compression),
        max_level=wconfig.max_level.name,
        target_shard_gb=wconfig.target_shard_gb,
        shard_z_chunks=wconfig.shard_z_chunks,
        batch_z_shards=wconfig.batch_z_shards,
        batch_z=wconfig.batch_z,
        frame_y=int(wconfig.volume_shape.y),
        frame_x=int(wconfig.volume_shape.x),
        dtype=str(blocks[0].dtype),
        **caps,
    )
    try:
        results.append(run, result)
    except Exception as e:  # a bad sink write must not lose the run's console output
        console.print(f"  [yellow](results not recorded: {type(e).__name__}: {e})[/]")
    _print_combo(run, result)
    return result


# ---------------------------------------------------------------------------
# Single-invocation entrypoint
# ---------------------------------------------------------------------------


def build_wconfig(blocks: list, batches: int, downscale: DownscaleType, **geometry) -> WriterConfig:
    """A WriterConfig for `batches` batches of the loaded frame shape. `geometry` overrides the writer's
    geometry defaults (max_level, shard_z_chunks, batch_z_shards, target_shard_gb) -- the sweep uses this."""
    y, x = blocks[0].shape[1], blocks[0].shape[2]
    wconfig = WriterConfig(
        volume_shape=UIVec3D(z=BATCH_SIZE * batches, y=y, x=x),
        voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
        downscale_type=downscale,
        **geometry,
    )
    if wconfig.batch_z != BATCH_SIZE:
        raise SystemExit(
            f"batch_z={wconfig.batch_z} != BATCH_SIZE={BATCH_SIZE}; fix max_level/shard_z_chunks/batch_z_shards"
        )
    return wconfig


def load_blocks(samples: int) -> list:
    """Load `samples` real blocks once and validate they share a frame shape (the batches rotate them)."""
    blocks = [load_real_block(ref) for ref in CATALOG[:samples]]
    if len({b.shape[1:] for b in blocks}) != 1:
        raise SystemExit("samples have mismatched frame shapes; use same-resolution tiles")
    if any(b.shape[0] < BATCH_SIZE for b in blocks):
        raise SystemExit(f"each sample must provide >= BATCH_SIZE={BATCH_SIZE} frames")
    return blocks


def main(cfg: BenchConfig) -> None:
    load_voxel_env()
    clear_artifacts("pre-run")  # self-heal any residue a prior killed run left before writing fresh data
    blocks = load_blocks(cfg.samples)
    wconfig = build_wconfig(blocks, cfg.batches, cfg.downscale)

    caps = _concurrency()
    run_id = new_run_id()
    results = Results(RESULTS_PATH, bench="write", run_id=run_id, packages=PACKAGES)
    _print_header(cfg, wconfig, blocks, run_id, caps)

    n = 0
    try:
        for be in cfg.backends:  # one writer per backend (backend is fixed at construction)
            bn = be.name.lower()
            writer = OMEZarrWriter(backend=be, slots=cfg.slots)
            try:
                for mode in cfg.modes:
                    label, storage = _storage(mode, bn)
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
                            fps=cfg.fps,
                            batches=cfg.batches,
                            samples=cfg.samples,
                            slots=cfg.slots,
                        )
                        n += 1
                    except Exception as e:  # one combo failing shouldn't abort the others
                        console.print(
                            f"[red]  {bn}/{label} FAILED {type(e).__name__}: {str(e).splitlines()[0][:120]}[/]"
                        )
            finally:
                writer.close()
    finally:
        if cfg.keep:
            console.print(
                f"\n[yellow]--keep[/]: left local under {LOCAL_ROOT} and VAST under {S3_ROOT} (next run clears it)"
            )
        else:
            clear_artifacts("cleanup")

    console.print(f"[dim]recorded {n} row(s) -> {RESULTS_PATH}[/]")


def _parse_args() -> BenchConfig:
    p = argparse.ArgumentParser(description="write real frames through OMEZarrWriter to Local/DirectS3/StagedS3")
    p.add_argument("--fps", type=float, default=6.0, help="simulated capture rate (default 6)")
    p.add_argument(
        "--downscale",
        type=DownscaleType,
        choices=list(DownscaleType),
        default=DownscaleType.GAUSSIAN,
        help="pyramid downsample method (default gaussian)",
    )
    p.add_argument("--backends", default="ts", help="comma-separated backends: ts,zarrs (default ts)")
    p.add_argument("--modes", default=",".join(MODE_KEYS), help="storage modes: local,direct,staged (default all)")
    p.add_argument("--slots", type=int, default=4, help="ring depth / batches in flight (default 4; ~batch_z RAM each)")
    p.add_argument("--batches", type=int, default=5, help="batches written back-to-back (default 5)")
    p.add_argument("--samples", type=int, default=2, help=f"samples to rotate through, 1..{len(CATALOG)} (default 2)")
    p.add_argument("--keep", action="store_true", help="keep local + VAST artifacts after the run (default: clear)")
    a = p.parse_args()

    try:
        backends = tuple(BACKEND_KEYS[b.strip().lower()] for b in a.backends.split(","))
    except KeyError as e:
        p.error(f"unknown backend {e}; choose from {sorted(BACKEND_KEYS)}")
    modes = tuple(m.strip().lower() for m in a.modes.split(","))
    if bad := [m for m in modes if m not in MODE_KEYS]:
        p.error(f"unknown mode(s) {bad}; choose from {list(MODE_KEYS)}")
    if not 1 <= a.samples <= len(CATALOG):
        p.error(f"--samples must be 1..{len(CATALOG)}")
    if a.slots < 2:
        p.error("--slots must be >= 2 (the writer needs at least 2 ring slots)")
    if a.batches < 1:
        p.error("--batches must be >= 1")
    return BenchConfig(
        fps=a.fps,
        slots=a.slots,
        batches=a.batches,
        samples=a.samples,
        downscale=a.downscale,
        backends=backends,
        modes=modes,
        keep=a.keep,
    )


if __name__ == "__main__":
    main(_parse_args())
