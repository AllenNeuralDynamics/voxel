"""Measure the true VAST S3 write ceiling via s5cmd — the StagedS3 uploader (Go, many workers), far
more concurrent than boto3's ~0.85 GB/s. Stages incompressible files to local scratch, then s5cmd-
uploads them at a sweep of --numworkers, reporting sustained GB/s per level. Tells us how much of the
25 GbE wire (~3.1 GB/s) is actually reachable — i.e. whether the writer's StagedS3 path can absorb
less-compressible (raw) data, or whether VAST/the software caps it well below the wire.

    uv run python bench/s3_write_ceiling.py [--total-gb 16] [--obj-mb 256]

Writes to a local scratch dir + s3://aind-stage/scratch/walter/_s5cmdbench (VAST); cleaned up after.
Needs VAST creds — loaded from ~/.voxel/.env via vxl.system.load_voxel_env (same as the app).
"""

import argparse
import shutil
import time
from pathlib import Path

import boto3
import numpy as np
from botocore.client import BaseClient
from botocore.config import Config
from cloudpathlib import S3Path
from ome_zarr_writer.transfer import TransferJob, run_s5cmd

from vxl.system import load_voxel_env
from vxlib import S3Store

VAST = S3Store(endpoint="http://10.128.113.13", region="aind")
S3_BUCKET = "aind-stage"
S3_PREFIX = "scratch/walter/_s5cmdbench"
S3_ROOT = S3Path(f"s3://{S3_BUCKET}/{S3_PREFIX}")
SCRATCH = Path.home() / ".voxel" / "scratch" / "_s5cmdbench"
NUMWORKERS = [64, 128, 256]  # s5cmd parallelism per invocation


def _s3() -> BaseClient:
    return boto3.client("s3", endpoint_url=VAST.endpoint, config=Config(region_name=VAST.region))


def cleanup() -> None:
    shutil.rmtree(SCRATCH, ignore_errors=True)
    s3 = _s3()
    deleted = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX + "/"):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objs:
            s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": objs})
            deleted += len(objs)
    print(f"\ncleanup: removed local scratch + {deleted} VAST objects")


def main() -> None:
    parser = argparse.ArgumentParser(description="measure s5cmd write throughput to VAST")
    parser.add_argument("--total-gb", type=float, default=16.0, help="total data to upload per level")
    parser.add_argument("--obj-mb", type=int, default=256, help="per-object size (staged shard)")
    args = parser.parse_args()

    load_voxel_env()
    n = max(1, round(args.total_gb * 1024 / args.obj_mb))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    # Stage incompressible files once. The same random bytes reused per file is fine — they're distinct
    # keys, so s5cmd still moves n * obj_mb over the wire (VAST doesn't dedup across keys).
    payload = np.random.default_rng(0).integers(0, 256, args.obj_mb * 1024 * 1024, dtype=np.uint8).tobytes()
    print(f"staging {n} x {args.obj_mb}MB = {n * args.obj_mb / 1024:.1f} GB to {SCRATCH} ...", flush=True)
    files = []
    for i in range(n):
        p = SCRATCH / f"obj_{i:04d}.bin"
        p.write_bytes(payload)
        files.append(p)
    print(f"uploading via s5cmd -> {S3_ROOT} | endpoint {VAST.endpoint} region {VAST.region}\n")

    try:
        for nw in NUMWORKERS:
            jobs = [TransferJob(src=p, dest=S3_ROOT / f"nw{nw}" / p.name) for p in files]
            t0 = time.perf_counter()
            moved = run_s5cmd(jobs, VAST, numworkers=nw, retry_count=3)
            dt = time.perf_counter() - t0
            print(f"  numworkers={nw:>3}: {moved / 1e9:5.1f} GB in {dt:6.2f}s -> {moved / 1e9 / dt * 1000:7.0f} MB/s "
                  f"({moved / 1e9 / dt:.2f} GB/s)")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
