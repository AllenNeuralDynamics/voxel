"""Measure raw S3 PUT bandwidth to the configured remote.

The DirectS3 target (see ~/.voxel/system.yaml) is an on-prem VAST S3 endpoint over the LAN
(endpoint http://10.128.113.13, region "aind", root aind-stage/scratch/walter) -- NOT AWS. So this
measures LAN + VAST ingest, which can be far higher than internet egress. It pushes INCOMPRESSIBLE
random objects at increasing concurrency to find where aggregate PUT throughput saturates (the raw
ceiling the writer's flush can't exceed), then deletes everything it wrote.

Run in a shell that has the same AWS creds as `uv run voxel`:
    uv run python bench/s3_put_bandwidth.py

Writes to s3://aind-stage/scratch/walter/_bwtest/ (temp; cleaned up in a finally, incl. on Ctrl+C).
"""

import concurrent.futures as cf
import time

import boto3
import numpy as np
from botocore.config import Config

from vxl.system import load_voxel_env

ENDPOINT = "http://10.128.113.13"
REGION = "aind"
BUCKET = "aind-stage"
PREFIX = "scratch/walter/_bwtest"
OBJ_MB = 32  # per-object size (roughly a shard); incompressible random bytes
CONCURRENCY = [1, 4, 16, 64]  # parallel in-flight PUTs
OBJS_PER_THREAD = 2  # objects per level = concurrency * this (keeps every thread busy)


def main() -> None:
    load_voxel_env()  # load ~/.voxel/.env (AWS_* creds + endpoint) into the process, same as the app
    peak = max(CONCURRENCY)
    cfg = Config(region_name=REGION, max_pool_connections=peak + 8, retries={"max_attempts": 3})
    s3 = boto3.client("s3", endpoint_url=ENDPOINT, config=cfg)
    payload = np.random.default_rng(0).integers(0, 256, size=OBJ_MB * 1024 * 1024, dtype=np.uint8).tobytes()
    print(f"endpoint={ENDPOINT} region={REGION} bucket={BUCKET} prefix={PREFIX}")
    print(f"object={OBJ_MB} MB incompressible | concurrency levels={CONCURRENCY}\n")

    def put(i: int) -> None:
        s3.put_object(Bucket=BUCKET, Key=f"{PREFIX}/obj_{i:06d}.bin", Body=payload)

    idx = 0
    try:
        put(idx)  # warm up: TCP/TLS/handshake outside the timed section
        idx += 1
        for c in CONCURRENCY:
            n = c * OBJS_PER_THREAD
            batch = list(range(idx, idx + n))
            idx += n
            t0 = time.perf_counter()
            with cf.ThreadPoolExecutor(max_workers=c) as ex:
                list(ex.map(put, batch))
            dt = time.perf_counter() - t0
            mb = n * OBJ_MB
            print(
                f"  concurrency={c:>3}: {n:>3} x {OBJ_MB}MB = {mb / 1024:5.2f} GB in {dt:6.2f}s "
                f"-> {mb / dt:8.1f} MB/s ({mb / dt / 1024:.2f} GB/s)"
            )
    finally:
        # Delete everything under the temp prefix (robust even if a PUT failed mid-run).
        print("\ncleaning up temp objects...")
        paginator = s3.get_paginator("list_objects_v2")
        deleted = 0
        for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX + "/"):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                s3.delete_objects(Bucket=BUCKET, Delete={"Objects": objs})
                deleted += len(objs)
        print(f"deleted {deleted} objects.")


if __name__ == "__main__":
    main()
