"""Shared config for the storage benches (transfer_speed, and future read/listing benches). Holds the S3
target + local scratch; each bench sets its own results path (`RESULTS_DIR / <bench> / <host>.jsonl`)."""

from pathlib import Path

from cloudpathlib import S3Path

from bench.config import BENCH_S3_BUCKET, BENCH_S3_ENDPOINT, BENCH_S3_PREFIX, BENCH_S3_REGION
from vxlib import S3Store

VAST = S3Store(endpoint=BENCH_S3_ENDPOINT, region=BENCH_S3_REGION)
S3_BUCKET = BENCH_S3_BUCKET
S3_PREFIX = f"{BENCH_S3_PREFIX}/_s5cmdbench"  # temp upload target (cleaned each run)
S3_ROOT = S3Path(f"s3://{S3_BUCKET}/{S3_PREFIX}")
SCRATCH = Path.home() / ".voxel" / "scratch" / "_s5cmdbench"
