"""Downsample-bench constants. Builds on the shared `bench.config` (HOST, RESULTS_DIR). No S3: this is a
pure in-RAM compute benchmark, so results append locally and share via `bench.sync` like any other bench."""

from bench.config import HOST, RESULTS_DIR

RESULTS_PATH = RESULTS_DIR / "downsample" / f"{HOST}.jsonl"
PACKAGES = ("numba", "numpy", "ome-zarr-writer", "tbb")  # versions recorded per run
