"""Pandas loaders for the write benchmark JSONL results. Depends only on pandas + the stdlib-only
`bench.config` (no writer/tensorstore, no creds), so these work in any REPL/script/notebook, even on a
machine without the writer installed. The stored records hold only raw observations; the derived columns
(fps, MB/s, ratio, drain, per-batch stage durations) are computed here -- one place, so they never drift.

    from bench.write.loaders import load, batch_timeline
    df = load()               # one row per backend x mode run, flattened + derived columns
    bt = batch_timeline()     # one row per (record, batch): stage start/end offsets + durations
"""

import pandas as pd

from bench.config import RESULTS_DIR

BENCH = "write"
_STAGES = ("collect", "process", "flush", "transfer")


def _read() -> pd.DataFrame:
    """Concatenate every per-machine file under `results/write/` (one JSONL per host; `bench.sync pull`
    brings in other machines' files). Records are self-describing, so mixing hosts is correct."""
    files = sorted((RESULTS_DIR / BENCH).glob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no results under {RESULTS_DIR / BENCH} (run the bench, then `bench.sync pull`)")
    frames = []
    for f in files:
        frame = pd.read_json(f, lines=True)
        # run_id identifies one benchmark invocation (and therefore an entire sweep), not one
        # measured point.  Keep a source-stable identity for each JSONL record so plots never merge
        # distinct sweep points that happen to share the same configuration or run_id.
        frame["record_id"] = [f"{f.name}:{i + 1}" for i in range(len(frame))]
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _drain(batches: list) -> float | None:
    ends = [b["flush"][1] for b in batches if b["flush"][1] is not None]
    collect_ends = [b["collect"][1] for b in batches if b["collect"][1] is not None]
    return max(ends) - max(collect_ends) if ends and collect_ends else None


def load() -> pd.DataFrame:
    """All `results/write/*.jsonl` as a flat DataFrame (nested git/machine/versions/run/result columns
    become dotted, e.g. `run.slots`, `result.wall_s`) with derived metric columns appended."""
    flat = pd.json_normalize(_read().to_dict(orient="records"))
    flat["frames"] = flat["run.batch_z"] * flat["run.batches"]
    flat["eff_fps"] = flat["frames"] / flat["result.collect_s"]
    flat["mb_s"] = flat["result.stored_bytes"] / 1e6 / flat["result.wall_s"]
    flat["ratio"] = flat["result.raw_bytes"] / flat["result.stored_bytes"]
    flat["drain_s"] = flat["result.batches"].map(_drain)
    return flat


def batch_timeline() -> pd.DataFrame:
    """One row per (record_id, batch) with each stage's [start, end] offset (seconds from the run's first
    collect) and its duration -- the shape for the per-batch Gantt and the flush-growth plot."""
    df = _read()
    rows = []
    for rec in df.to_dict(orient="records"):
        run, result = rec["run"], rec["result"]
        for b in result["batches"]:
            row = {
                "record_id": rec["record_id"],
                "run_id": rec["run_id"],
                "backend": run["backend"],
                "mode": run["mode"],
                "fps_target": run["fps_target"],
                "compression": run["compression"],
                "target_shard_gb": run["target_shard_gb"],
                "downscale": run["downscale"],
                "max_level": run["max_level"],
                "slots": run["slots"],
                "batch": b["batch"],
            }
            for stage in _STAGES:
                s, e = b[stage]
                row[f"{stage}_start"] = s
                row[f"{stage}_end"] = e
                row[f"{stage}_s"] = None if s is None or e is None else e - s
            rows.append(row)
    return pd.DataFrame(rows)
