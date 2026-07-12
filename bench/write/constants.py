"""Write-bench-specific config: the temp write target (S3 + local scratch) and this machine's results
file. Builds on the shared `bench.config` (S3 store, HOST, RESULTS_DIR)."""

from pathlib import Path

from bench.config import (
    BENCH_S3_BUCKET,
    BENCH_S3_ENDPOINT,
    BENCH_S3_PREFIX,
    BENCH_S3_REGION,
    HOST,
    RESULTS_DIR,
)
from vxlib import S3Store

VAST = S3Store(endpoint=BENCH_S3_ENDPOINT, region=BENCH_S3_REGION)
S3_BUCKET = BENCH_S3_BUCKET
S3_PREFIX = f"{BENCH_S3_PREFIX}/_writebench"  # temp write target (cleaned each run)
S3_ROOT = f"s3://{S3_BUCKET}/{S3_PREFIX}"
LOCAL_ROOT = Path.home() / ".voxel" / "store" / "_writebench"
SCRATCH = Path.home() / ".voxel" / "scratch" / "_writebench"

# One results file per machine (results/write/<host>.jsonl): each machine owns its file, so appends never
# conflict across machines. Share by syncing to the common S3 prefix -- see bench/sync.py.
RESULTS_PATH = RESULTS_DIR / "write" / f"{HOST}.jsonl"

# Package versions recorded with every run (cross-version comparisons need this).
PACKAGES = ("tensorstore", "zarr", "zarrs", "numpy", "numcodecs", "obstore", "ome-zarr-writer")
