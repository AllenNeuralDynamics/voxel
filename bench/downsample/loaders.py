"""Pandas loaders for the downsample benchmark results. Depends only on pandas + numpy + the stdlib-only
`bench.config` (no writer, no creds). Stored records hold raw observations (time_s, block dims); GB/s is
derived here.

    from bench.downsample.loaders import load
    df = load()   # one row per (reduction, threads) point, with l0_gb + gb_s derived
"""

import numpy as np
import pandas as pd

from bench.config import RESULTS_DIR

BENCH = "downsample"


def _read() -> pd.DataFrame:
    files = sorted((RESULTS_DIR / BENCH).glob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no results under {RESULTS_DIR / BENCH} (run the bench, then `bench.sync pull`)")
    return pd.concat([pd.read_json(f, lines=True) for f in files], ignore_index=True)


def load() -> pd.DataFrame:
    """All `results/downsample/*.jsonl` flattened, with `l0_gb` and `gb_s` (throughput) derived."""
    flat = pd.json_normalize(_read().to_dict(orient="records"))
    itemsize = flat["run.dtype"].map(lambda d: np.dtype(d).itemsize)
    flat["l0_gb"] = flat["run.block_z"] * flat["run.block_y"] * flat["run.block_x"] * itemsize / 1e9
    flat["gb_s"] = flat["l0_gb"] / flat["result.time_s"]
    return flat
