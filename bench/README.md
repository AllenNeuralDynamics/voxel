# Benchmarks

Throughput/behavior benchmarks for the OME-Zarr writer, with an append-only results log and ready-to-run
analysis. Every recorded number is **reproducible** — git commit + dirty, library versions, machine
identity, and full settings travel with each record — and we store **raw observations only**: fps, MB/s,
ratios, and drain tails are *derived in analysis*, never in the record.

`bench` is a **virtual uv workspace member** (`[tool.uv] package = false`): managed in the workspace with
its own deps, but never built or published. Run its benches as modules from the repo root.

## Layout

```
bench/
  harness.py        # generic: provenance + append-only JSONL sink (bench-agnostic)
  data.py           # real exaSPIM frame loader (public S3, anonymous)
  sync.py           # S3 push/pull for results (works for any bench)
  config.py         # shared constants: RESULTS_DIR, HOST, env-configurable BENCH_S3_*  (stdlib only)
  write/            # I/O throughput bench — run.py, sweep.py, loaders.py, analysis.py, constants.py
  downsample/       # pyramid compute bench — run.py, loaders.py, analysis.py, constants.py
  storage/          # storage benches (a category) — transfer_speed.py [+ more], loaders.py, constants.py
  results/<bench>/<host>.jsonl   # append target, one file per machine (git-ignored; shared via sync.py)
```

Each bench records to `results/<bench-name>/<host>.jsonl` (e.g. `write`, `downsample`, `transfer_speed`).
A "bench folder" is usually one bench (`write`, `downsample`); `storage/` is a **category** holding several
related benches (each a named script sharing `constants.py`).

The benchmarking S3 store (write target + shared results) is env-configurable, defaulting to the VAST
scratch used here: `VOXEL_BENCH_S3_ENDPOINT`, `VOXEL_BENCH_S3_REGION`, `VOXEL_BENCH_S3_BUCKET`,
`VOXEL_BENCH_S3_PREFIX`.

## Run

```bash
# single run — defaults: --fps 6 --backends ts --modes local,direct,staged --slots 4 --batches 5 --samples 2
uv run -m bench.write.run --fps 16 --backends ts,zarrs --modes local --slots 4 --batches 20

# sweep a parameter grid (edit SWEEP in bench/write/sweep.py). Loads data once, reuses one writer per
# (backend, slots); records every point to the same results file as single runs, so they pool.
uv run -m bench.write.sweep --batches 20 --samples 1

# downsample: production pyramid kernel (pyramids_3d_numba) throughput vs numba thread count
uv run -m bench.downsample.run --threads=1,2,4,8,16,32,64 --reductions=gaussian,mean

# storage: s5cmd -> S3 write ceiling (transfer_speed is one storage bench; more can be added later)
uv run -m bench.storage.transfer_speed --total-gb 16 --numworkers 64,128,256
```

Concurrency caps are read from the environment and recorded with each run (fixed for a whole sweep):

```bash
VOXEL_NUMBA_THREADS=16 VOXEL_TS_CONCURRENCY=16 VOXEL_ZARRS_SHARD_WORKERS=16 \
  uv run -m bench.write.run --backends ts --modes local
```

`--keep` leaves the written data in place (cleared on the next run); otherwise the bench clears its local
temp and VAST scratch both before (self-healing killed runs) and after each run.

## Share across machines

Each machine appends to its own `results/write/<host>.jsonl`, so there are no cross-machine write
conflicts. Pool them through a shared S3 prefix (no git involved):

```bash
uv run -m bench.sync push     # upload this machine's result files
uv run -m bench.sync pull      # download every other machine's files
```

`pull` never overwrites this machine's own file. Records are self-describing (each carries `machine.host`,
`git.commit`, `versions`), so analysis over the pooled directory is just a `groupby`.

## Analyse

The write bench renders a **curated standalone HTML report** — no server, no chart-building:

```bash
uv run -m bench.sync pull             # optional: pull other machines' results first
uv run -m bench.write.report --open   # writes results/write/report.html and opens it
```

It contains a summary table plus fixed, meaningful plotly figures: throughput vs shard size (by codec),
the compression ratio/throughput Pareto, per-batch **flush growth** (the drain-falling-behind signal), a
batch-pipeline **Gantt** for the worst-drain run, and a cross-machine comparison when >1 host is present.
Analysis reads whatever is in `results/write/` locally, so **cross-machine means pulling first**.

The report needs the `analysis` deps — present after `uv sync --all-packages --all-extras --all-groups`
(then plain `uv run` finds them; `--group analysis` won't resolve at the root since it's a member group).

Loaders are plain pandas (no writer stack, no creds) if you prefer a REPL:

```python
from bench.write.loaders import load, batch_timeline   # run from the repo root
df = load()               # one row per backend x mode run, derived cols (eff_fps, mb_s, ratio, drain_s)
bt = batch_timeline()     # one row per batch: stage start/end offsets + durations (Gantt + flush growth)
```

## Adding a new bench

Reuse `harness.py`, `data.py`, `sync.py`, `config.py` verbatim; give each bench its own `run`/`result`
pydantic models (raw observations only) and record to `results/<name>/<host>.jsonl`. Two shapes:

- **Full bench** (like `write`): a `bench/<name>/` folder with `run.py`, optional `sweep.py`, `loaders.py`,
  `report.py` (curated plotly HTML — the preferred analysis shape), `constants.py`.
- **Category** (like `storage`): a folder of several lean, descriptively-named scripts (`transfer_speed.py`,
  …) sharing one `constants.py` and `loaders.py`.

(`downsample/` still ships a marimo `analysis.py` — the older chart-builder pattern, migrating to `report.py`.)

`sync.py` already handles every bench's results, and the marimo explorer pattern (`analysis.py`) transfers
directly.
