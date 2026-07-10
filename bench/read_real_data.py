"""Load a block of REAL acquired frames from a public S3 OME-Zarr into RAM (anonymous, no creds).

`load_real_block()` opens a full-res exaSPIM tile anonymously and returns N z-slices from the middle
as a (N, y, x) uint16 array — real, uncompressed data to use in place of the simulated camera (whose
identical broadcast frames compress unrealistically well). 128 frames == one writer batch (batch_z).

    uv run python bench/read_real_data.py            # standalone: read + report
    from read_real_data import load_real_block        # or import the loader

Public dataset (AWS Open Data, us-west-2) — reads only, no credentials.
"""

import time

import numpy as np
from cloudpathlib import S3Path
from ome_zarr_writer.array.ts import TSArrayReader

from vxlib import S3Store

TILE = (
    "s3://aind-open-data/exaSPIM_794491_2025-10-21_12-31-25_processed_2025-10-26_12-28-14"
    "/denoised_full_res/SPIM.ome.zarr/tile_000012_ch_488.zarr"
)
REGION = "us-west-2"  # aind-open-data lives here
LEVEL = "0"  # full-res level of the multiscale tile
Z0 = 15000  # start z (middle of the stack)
N = 128  # frames to read (one writer batch)


def open_full_res(*, verbose: bool = True) -> TSArrayReader:
    """Open the full-res array anonymously, trying level-0-vs-tile and zarr v3-vs-v2."""
    store = S3Store(region=REGION)
    attempts = [(f"{TILE}/{LEVEL}", True), (f"{TILE}/{LEVEL}", False), (TILE, True), (TILE, False)]
    for path, v3 in attempts:
        try:
            reader = TSArrayReader(S3Path(path), store=store, anonymous=True, v3=v3)
            if verbose:
                print(f"opened {path}  (zarr v{'3' if v3 else '2'})  shape={reader.shape}")
            return reader
        except Exception as e:  # try the next layout/format
            if verbose:
                print(f"  x {path} v{'3' if v3 else '2'}: {type(e).__name__}: {str(e).splitlines()[0][:80]}")
    raise SystemExit("could not open the array (tried level 0 and the tile, v3 and v2)")


def load_real_block(z0: int = Z0, n: int = N, *, verbose: bool = True) -> np.ndarray:
    """Read `n` z-slices starting at `z0` (clamped in-range) into RAM as a (n, y, x) array."""
    reader = open_full_res(verbose=verbose)
    z, y, x = reader.shape[-3], reader.shape[-2], reader.shape[-1]  # read_3d collapses leading axes
    z0 = max(0, min(z0, z - n))
    if verbose:
        print(f"reading {n} frames @ z0={z0}/{z} (y={y} x={x}, ~{n * y * x * 2 / 1e9:.1f} GB)...", flush=True)
    t0 = time.perf_counter()
    block = reader.read_3d(z0=z0, n=n)
    if verbose:
        gb, dt = block.nbytes / 1e9, time.perf_counter() - t0
        print(f"read {block.shape} {block.dtype} = {gb:.2f} GB in {dt:.1f}s -> {gb / dt * 1000:.0f} MB/s "
              f"| min={int(block.min())} max={int(block.max())} mean={float(block.mean()):.1f}")
    return block


if __name__ == "__main__":
    load_real_block()
