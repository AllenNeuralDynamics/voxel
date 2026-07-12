"""Benchmarks for the OME-Zarr writer. A virtual uv workspace member (not built/published) -- run its
benches as modules from the repo root, e.g. `uv run -m bench.write.run` / `uv run -m bench.write.sweep`.

VAST creds are loaded (via `vxl.system.load_voxel_env`) inside the run/sync paths that need them, not here
-- so importing the pandas-only analysis (`loaders`, `report`) stays creds-free and portable.
"""
