"""Measure the S3 write ceiling via s5cmd -- the production StagedS3 uploader (`run_s5cmd`, Go, many
workers), far more concurrent than boto3. Stages incompressible files to local scratch once, then uploads
them at a sweep of s5cmd worker counts, recording sustained GB/s per level. Tells us how much of the wire
(~3.1 GB/s on 25 GbE) is reachable -- i.e. the ceiling the writer's StagedS3 flush runs against.

    uv run -m bench.storage.transfer_speed [--total-gb 16] [--obj-mb 256] [--numworkers 64,128,256]

Uploads to the VAST scratch prefix (cleaned after). Needs VAST creds from ~/.voxel/.env via load_voxel_env.
Records one row per worker count to results/transfer_speed/<host>.jsonl; analyse with `bench.storage.loaders`.
"""

import argparse
import shutil
import time

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from numpy.random import default_rng
from ome_zarr_writer.transfer import TransferJob, run_s5cmd
from pydantic import BaseModel
from rich import box
from rich.console import Console
from rich.table import Table

from bench.config import HOST, RESULTS_DIR
from bench.harness import Results, new_run_id
from bench.storage.constants import S3_BUCKET, S3_PREFIX, S3_ROOT, SCRATCH, VAST
from vxl.system import load_voxel_env

console = Console()

BENCH = "transfer_speed"
RESULTS_PATH = RESULTS_DIR / BENCH / f"{HOST}.jsonl"
PACKAGES = ("s5cmd", "ome-zarr-writer", "boto3")  # versions recorded per run


class TransferRun(BaseModel):
    numworkers: int  # s5cmd parallelism
    obj_mb: int  # per-object size (a staged shard)
    n_objects: int
    retry_count: int
    endpoint: str | None  # which S3 endpoint -- ceilings are endpoint-specific (None = AWS default)
    region: str | None


class TransferResult(BaseModel):
    moved_bytes: int  # bytes s5cmd reported moving (throughput = moved_bytes / time_s)
    time_s: float


def _s3() -> BaseClient:
    return boto3.client(
        "s3", endpoint_url=VAST.endpoint, config=Config(region_name=VAST.region, s3={"addressing_style": "path"})
    )


def cleanup() -> None:
    shutil.rmtree(SCRATCH, ignore_errors=True)
    try:
        s3 = _s3()
        deleted = 0
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX + "/"):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": objs})
                deleted += len(objs)
        console.print(f"[dim]cleanup: removed local scratch + {deleted} VAST objects[/]")
    except Exception as e:
        console.print(f"[dim]cleanup: local scratch removed; VAST cleanup FAILED ({type(e).__name__})[/]")


def run(*, total_gb: float, obj_mb: int, numworkers: tuple[int, ...], retry_count: int = 3) -> None:
    load_voxel_env()
    n = max(1, round(total_gb * 1024 / obj_mb))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    # Stage incompressible files once. Reusing the same random bytes per file is fine -- distinct keys, so
    # s5cmd still moves n * obj_mb over the wire (VAST doesn't dedup across keys).
    payload = default_rng(0).integers(0, 256, obj_mb * 1024 * 1024, dtype="uint8").tobytes()
    files = []
    for i in range(n):
        p = SCRATCH / f"obj_{i:04d}.bin"
        p.write_bytes(payload)
        files.append(p)

    run_id = new_run_id()
    results = Results(RESULTS_PATH, bench=BENCH, run_id=run_id, packages=PACKAGES)
    console.rule(f"[bold]transfer_speed bench[/]  run_id={run_id}")
    console.print(
        f"staged {n} x {obj_mb}MB = {n * obj_mb / 1024:.1f} GB -> s5cmd upload to {S3_ROOT} "
        f"| endpoint {VAST.endpoint} region {VAST.region}"
    )
    table = Table(box=box.SIMPLE)
    for col in ("numworkers", "GB", "s", "GB/s"):
        table.add_column(col, justify="right")

    try:
        for nw in numworkers:
            jobs = [TransferJob(src=p, dest=S3_ROOT / f"nw{nw}" / p.name) for p in files]
            t0 = time.perf_counter()
            moved = run_s5cmd(jobs, VAST, numworkers=nw, retry_count=retry_count)
            dt = time.perf_counter() - t0
            results.append(
                TransferRun(
                    numworkers=nw,
                    obj_mb=obj_mb,
                    n_objects=n,
                    retry_count=retry_count,
                    endpoint=VAST.endpoint,
                    region=VAST.region,
                ),
                TransferResult(moved_bytes=moved, time_s=round(dt, 3)),
            )
            table.add_row(str(nw), f"{moved / 1e9:.1f}", f"{dt:.2f}", f"{moved / 1e9 / dt:.2f}")
    finally:
        cleanup()

    console.print(table)
    console.print(f"[dim]recorded {len(numworkers)} rows -> {RESULTS_PATH}[/]")


def _parse_args() -> dict:
    p = argparse.ArgumentParser(description="measure the s5cmd -> S3 write ceiling")
    p.add_argument("--total-gb", type=float, default=16.0, help="total data uploaded per worker count")
    p.add_argument("--obj-mb", type=int, default=256, help="per-object size (staged shard)")
    p.add_argument("--numworkers", default="64,128,256", help="comma list of s5cmd worker counts")
    a = p.parse_args()
    return {"total_gb": a.total_gb, "obj_mb": a.obj_mb, "numworkers": tuple(int(w) for w in a.numworkers.split(","))}


if __name__ == "__main__":
    run(**_parse_args())
