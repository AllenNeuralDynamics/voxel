"""Shared benchmark config: where results live, this machine's id, and the (env-configurable) S3 store.

Stdlib-only, so lightweight consumers (`bench.sync`, the analysis loaders) import these without pulling in
the writer / tensorstore stack that `bench.data` needs. Per-bench specifics live in `bench.<name>.constants`.
"""

import os
import platform
import re
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"  # per-machine JSONL under results/<bench>/<host>.jsonl
HOST = re.sub(r"[^A-Za-z0-9._-]", "_", platform.node()) or "unknown"  # this machine's results-file key

# S3 store for benchmarking: the write target (DirectS3/StagedS3) and the shared results sink. Env-
# configurable so a different deployment can point elsewhere; defaults are the VAST scratch used here.
BENCH_S3_ENDPOINT = os.environ.get("VOXEL_BENCH_S3_ENDPOINT", "http://10.128.113.13")
BENCH_S3_REGION = os.environ.get("VOXEL_BENCH_S3_REGION", "aind")
BENCH_S3_BUCKET = os.environ.get("VOXEL_BENCH_S3_BUCKET", "aind-stage")
BENCH_S3_PREFIX = os.environ.get("VOXEL_BENCH_S3_PREFIX", "scratch/walter")  # base; sub-prefixes below
