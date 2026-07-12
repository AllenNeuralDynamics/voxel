"""Pandas loaders for the storage benches (transfer_speed, and future read/listing benches). pandas +
stdlib-only `bench.config` (no writer, no creds).

    from bench.storage.loaders import load
    df = load()                    # transfer_speed by default
    df = load("transfer_speed")    # or name a specific storage bench
"""

import pandas as pd

from bench.config import RESULTS_DIR


def load(bench: str = "transfer_speed") -> pd.DataFrame:
    """All `results/<bench>/*.jsonl` flattened. For throughput benches (moved_bytes + time_s), derives
    `gb_moved` and `gb_s`."""
    files = sorted((RESULTS_DIR / bench).glob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no results under {RESULTS_DIR / bench} (run the bench, then `bench.sync pull`)")
    df = pd.concat([pd.read_json(f, lines=True) for f in files], ignore_index=True)
    flat = pd.json_normalize(df.to_dict(orient="records"))
    if {"result.moved_bytes", "result.time_s"} <= set(flat.columns):
        flat["gb_moved"] = flat["result.moved_bytes"] / 1e9
        flat["gb_s"] = flat["gb_moved"] / flat["result.time_s"]
    return flat
