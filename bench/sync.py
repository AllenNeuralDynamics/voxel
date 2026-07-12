"""Sync benchmark results with a shared S3 prefix. One JSONL file per machine
(`results/<bench>/<host>.jsonl`) -- each machine owns its file, so there are never write conflicts.
`push` uploads this machine's files (overwriting its own remote copy); `pull` downloads every *other*
machine's files, leaving this machine's local file untouched. Analysis (`bench.write.loaders`) globs the
local directory, so after a `pull` every machine's runs are available locally.

    uv run -m bench.sync push        # upload this host's result files
    uv run -m bench.sync pull         # download other hosts' result files

The S3 store is `bench.config.BENCH_S3_*` (env-configurable). Needs creds from ~/.voxel/.env via load_voxel_env.
"""

import argparse

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from bench.config import BENCH_S3_BUCKET, BENCH_S3_ENDPOINT, BENCH_S3_PREFIX, BENCH_S3_REGION, HOST, RESULTS_DIR
from vxl.system import load_voxel_env

RESULTS_PREFIX = f"{BENCH_S3_PREFIX}/benchmarks"  # persistent shared results (not the temp write target)


def _s3() -> BaseClient:
    load_voxel_env()
    cfg = Config(region_name=BENCH_S3_REGION, s3={"addressing_style": "path"})
    return boto3.client("s3", endpoint_url=BENCH_S3_ENDPOINT, config=cfg)


def push() -> None:
    """Upload every local `results/<bench>/<HOST>.jsonl` to the shared prefix (overwrites own remote)."""
    s3 = _s3()
    files = sorted(RESULTS_DIR.glob(f"*/{HOST}.jsonl"))
    if not files:
        print(f"nothing to push (no results/*/{HOST}.jsonl -- run a bench first)")
        return
    for f in files:
        key = f"{RESULTS_PREFIX}/{f.parent.name}/{f.name}"
        s3.upload_file(str(f), BENCH_S3_BUCKET, key)
        print(f"pushed {f.relative_to(RESULTS_DIR)} -> s3://{BENCH_S3_BUCKET}/{key}")


def pull() -> None:
    """Download every other machine's result file into `results/<bench>/`, skipping this host's own
    file so unpushed local runs are never clobbered."""
    s3 = _s3()
    n = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BENCH_S3_BUCKET, Prefix=RESULTS_PREFIX + "/"):
        for obj in page.get("Contents", []):
            rel = obj["Key"][len(RESULTS_PREFIX) + 1 :]  # <bench>/<host>.jsonl
            if not rel.endswith(".jsonl") or rel.endswith(f"/{HOST}.jsonl"):
                continue  # skip non-results and this machine's own file
            dest = RESULTS_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(BENCH_S3_BUCKET, obj["Key"], str(dest))
            print(f"pulled {rel}")
            n += 1
    print(f"pulled {n} file(s) from s3://{BENCH_S3_BUCKET}/{RESULTS_PREFIX}/")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="sync benchmark results with the shared S3 prefix")
    p.add_argument("action", choices=["push", "pull"])
    args = p.parse_args()
    (push if args.action == "push" else pull)()
