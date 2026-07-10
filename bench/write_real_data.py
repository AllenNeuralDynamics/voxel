"""Bench: write REAL frames through the actual writer to Local / DirectS3 / StagedS3.

Reads one batch of real denoised exaSPIM frames (`read_real_data.load_real_block`, N = BATCH_SIZE) and
writes it as NUM_BATCHES back-to-back batches through the real `OMEZarrWriter`, pacing the add loop at
FPS so collect/flush overlap like a live acquisition. Per backend it reports wall time and effective
fps, then reads the writer's own `metrics.json` to print the per-batch pipeline timeline (collect /
process / flush offsets, so overlap + drain tail are visible) and the REAL compression ratio (raw
bytes the codec ingested vs actual bytes stored) — the numbers behind the VAST-flush question.

    uv run python bench/write_real_data.py [--fps N] [--downscale mean|max|min|gaussian]  # defaults: --fps 6, mean

Each of the NUM_BATCHES batches reuses the same real block (batches compress independently). BATCH_SIZE
must be a multiple of 128 (the L7 chunk edge == writer batch_z). NUM_BATCHES > SLOTS forces ring rotation
(a batch must wait for an earlier slot's flush), so a slow flush shows as collect fps dropping below FPS.
Raise FPS to shrink the per-batch collect window and stress whether the flush keeps up.

Writes to a local temp dir + s3://aind-stage/scratch/walter/_writebench (VAST); cleaned up after.
Needs VAST creds — loaded from ~/.voxel/.env via vxl.system.load_voxel_env (same as the app).
"""

import argparse
import json
import shutil
import time
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
from read_real_data import load_real_block

from vxl.system import load_voxel_env
from vxlib import S3Store

BATCH_SIZE = 128  # frames per batch (== writer batch_z); must be a multiple of 128 (L7 chunk edge)
NUM_BATCHES = 5  # batches to write back-to-back (tests pipelined multi-batch flush)
FPS = 6.0  # simulated capture rate (default); override with --fps. Rebound in __main__ before main() runs.
SLOTS = min(NUM_BATCHES, 4)  # ring depth; matches the acquisition cap. NUM_BATCHES > SLOTS -> back-pressure
DOWNSCALE = DownscaleType.MEAN  # pyramid downsample method (default); override with --downscale. Rebound in __main__.

VAST = S3Store(endpoint="http://10.128.113.13", region="aind")
S3_BUCKET = "aind-stage"
S3_PREFIX = "scratch/walter/_writebench"
S3_ROOT = f"s3://{S3_BUCKET}/{S3_PREFIX}"
LOCAL_ROOT = Path.home() / ".voxel" / "store" / "_writebench"
SCRATCH = Path.home() / ".voxel" / "scratch" / "_writebench"

_STAGES = ("collecting", "processing", "flushing", "transferring")


def _s3() -> BaseClient:
    return boto3.client("s3", endpoint_url=VAST.endpoint, config=Config(region_name=VAST.region))


def stored_bytes(target: Path | S3Path | None) -> int:
    """Actual bytes on the store (compressed): sum local file sizes, or S3 object sizes under `target`.
    The writer's `flushed_bytes` is the *uncompressed* input, so this is how we get the real ratio."""
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


def summarize_metrics(metrics: dict, stored: int) -> None:
    """Print the per-batch pipeline timeline (stage offsets from run start, so overlap + drain tail are
    visible) and the real compression ratio (raw bytes the codec saw vs bytes actually stored)."""
    batches = [b for b in metrics["batches"] if b["collecting"]["started"]]
    if not batches:
        print("      (no completed batches)")
        return
    stamps = [
        datetime.fromisoformat(b[s][e]) for b in batches for s in _STAGES for e in ("started", "ended") if b[s][e]
    ]
    t0, tn = min(stamps), max(stamps)

    def off(ts: str | None) -> str:
        return f"{(datetime.fromisoformat(ts) - t0).total_seconds():5.1f}" if ts else "  -  "

    for b in batches:
        c, p, f, x = b["collecting"], b["processing"], b["flushing"], b["transferring"]
        line = (
            f"      b{b['batch_idx']}: collect {off(c['started'])}->{off(c['ended'])}  "
            f"process {off(p['started'])}->{off(p['ended'])}  flush {off(f['started'])}->{off(f['ended'])}"
        )
        if x["started"]:
            line += f"  xfer {off(x['started'])}->{off(x['ended'])}"
        print(line)
    raw = sum(b["flushed_bytes"] for b in batches)
    last_collect = max((datetime.fromisoformat(b["collecting"]["ended"]) - t0).total_seconds() for b in batches)
    span = (tn - t0).total_seconds()
    ratio = raw / stored if stored else float("nan")
    print(
        f"      span={span:.1f}s  drain_tail={span - last_collect:.1f}s  |  "
        f"{raw / 1e9:.0f}GB raw -> {stored / 1e9:.1f}GB stored ({ratio:.1f}x compression)"
    )


def write_once(writer: OMEZarrWriter, config: WriterConfig, storage: Storage, block, label: str) -> None:
    dw = writer.begin_stack(config, storage)  # DatasetWriter; its .target + metrics.json survive end_stack
    interval = 1.0 / FPS
    t0 = next_t = time.perf_counter()
    for _ in range(NUM_BATCHES):  # each batch reuses the same real block (batches compress independently)
        for i in range(BATCH_SIZE):
            writer.add_frame(block[i])
            next_t += interval  # pace at FPS; if the writer back-pressures, add_frame runs long and we fall behind
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
    t_add = time.perf_counter()
    writer.end_stack()
    t_end = time.perf_counter()

    frames = BATCH_SIZE * NUM_BATCHES
    collect_s, wall = t_add - t0, t_end - t0
    stored = stored_bytes(dw.target)
    print(
        f"\n  [{label}] wall={wall:.1f}s  collect={collect_s:.1f}s ({frames / collect_s:.1f} fps, target {FPS:.0f})  "
        f"store={stored / 1e9:.1f}GB @ {stored / 1e9 / wall * 1000:.0f} MB/s"
    )
    try:
        summarize_metrics(read_metrics(dw.target), stored)
    except Exception as e:  # metrics summary is best-effort, never fail the bench
        print(f"      (metrics.json unavailable: {type(e).__name__}: {e})")


def cleanup() -> None:
    shutil.rmtree(LOCAL_ROOT, ignore_errors=True)
    shutil.rmtree(SCRATCH, ignore_errors=True)
    s3 = _s3()
    deleted = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX + "/"):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objs:
            s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": objs})
            deleted += len(objs)
    print(f"\ncleanup: removed local temp + {deleted} VAST objects")


def main() -> None:
    load_voxel_env()
    block = load_real_block(n=BATCH_SIZE)
    config = WriterConfig(
        volume_shape=UIVec3D(z=BATCH_SIZE * NUM_BATCHES, y=block.shape[1], x=block.shape[2]),
        voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
        batch_z_shards=max(1, BATCH_SIZE // 128),
        downscale_type=DOWNSCALE,
    )
    if config.batch_z != BATCH_SIZE:
        raise SystemExit(f"BATCH_SIZE={BATCH_SIZE} must be a multiple of 128; got batch_z={config.batch_z}")
    print(
        f"\nframe={block.shape[1]}x{block.shape[2]} | batch_z={config.batch_z} x {NUM_BATCHES} batches "
        f"= {BATCH_SIZE * NUM_BATCHES} frames @ {FPS:.0f}fps | slots={SLOTS} | {config.compression} | "
        f"downscale={config.downscale_type}"
    )
    writer = OMEZarrWriter(slots=SLOTS)
    backends = [
        ("Local", Local(target=LOCAL_ROOT / "local")),
        ("DirectS3", DirectS3(target=S3Path(f"{S3_ROOT}/direct"), store=VAST)),
        ("StagedS3", StagedS3(scratch=SCRATCH, target=S3Path(f"{S3_ROOT}/staged"), store=VAST)),
    ]
    try:
        for label, storage in backends:
            try:
                write_once(writer, config, storage, block, label)
            except Exception as e:  # one backend failing shouldn't abort the others
                print(f"\n  [{label}] FAILED {type(e).__name__}: {str(e).splitlines()[0][:120]}")
    finally:
        writer.close()
        cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="write real frames to Local/DirectS3/StagedS3")
    parser.add_argument("--fps", type=float, default=FPS, help="simulated capture rate (default 6)")
    parser.add_argument(
        "--downscale",
        type=DownscaleType,
        choices=list(DownscaleType),
        default=DOWNSCALE,
        help="pyramid downsample method (default mean)",
    )
    _args = parser.parse_args()
    FPS = _args.fps  # module-scope rebind; write_once/main read the globals
    DOWNSCALE = _args.downscale
    main()
