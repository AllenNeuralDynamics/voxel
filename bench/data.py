"""Load blocks of REAL acquired frames from public S3 OME-Zarr tiles into RAM (anonymous, no creds).

The bench needs realistic pixels, not the simulated camera's identical broadcast frames (which compress
unrealistically well). `load_real_block` opens a full-res exaSPIM tile anonymously and returns a
`(n, y, x)` uint16 array from a z-window centred on real signal. 128 frames == one writer batch.

    uv run bench/data.py            # standalone: read the default block and report
    from data import CATALOG, load_real_block   # or import for the bench

Public dataset (AWS Open Data, us-west-2) -- read-only, unsigned.
"""

import time
from dataclasses import dataclass

import boto3
import numpy as np
from botocore import UNSIGNED
from botocore.config import Config as BotoConfig
from cloudpathlib import S3Path
from ome_zarr_writer.array.ts import TSArrayReader
from rich.console import Console

from vxlib import S3Store

REGION = "us-west-2"  # aind-open-data (the real-data source) lives here
LEVEL = "0"  # full-res level of the multiscale tile
BATCH_SIZE = 128  # frames per block == one writer batch (batch_z)

console = Console()


@dataclass(frozen=True)
class DataRef:
    """A reference to a block of real frames: an OME-Zarr tile `link` and a z-window [z_start, z_end).
    `v3` forces the Zarr format (None = auto-detect from the array metadata)."""

    link: str
    z_start: int
    z_end: int
    v3: bool | None = None

    @property
    def n(self) -> int:
        return self.z_end - self.z_start


# CATALOG: validated native-res RAW exaSPIM samples -- a tile plus a BATCH_SIZE z-window centred on that
# tile's peak-signal plane. In the 20-tile mosaic the middle tiles hold specimen while corners (e.g.
# tile_000000) are background; the trailing comment is the window's peak intensity. Each loaded 151 MP x
# BATCH_SIZE block is ~38 GB, so load only a couple per run.
_DS = "s3://aind-open-data/exaSPIM_786399_2026-04-14_17-47-27/SPIM.ome.zarr"
CATALOG = [
    DataRef(f"{_DS}/tile_000001_ch_488.zarr", 10496, 10496 + BATCH_SIZE),  # max ~12700 (level-0 validated)
    DataRef(f"{_DS}/tile_000004_ch_488.zarr", 7488, 7488 + BATCH_SIZE),  # max ~3600  (level-0 validated)
    DataRef(f"{_DS}/tile_000008_ch_488.zarr", 8128, 8128 + BATCH_SIZE),  # max ~4500  (level-0 validated)
    DataRef(f"{_DS}/tile_000002_ch_488.zarr", 11200, 11200 + BATCH_SIZE),  # max ~2800  (coarse survey)
    DataRef(f"{_DS}/tile_000006_ch_488.zarr", 7936, 7936 + BATCH_SIZE),  # max ~2400  (coarse survey)
]
DEFAULT_REF = CATALOG[0]


def _detect_v3(array_url: str) -> bool | None:
    """Pick the Zarr format from the array's metadata key (one unsigned HEAD, no failed open): v3 has
    `zarr.json`, v2 has `.zarray`. Returns None if neither is found (caller then probes)."""
    p = S3Path(array_url)
    s3 = boto3.client("s3", region_name=REGION, config=BotoConfig(signature_version=UNSIGNED))
    base = p.key.rstrip("/")

    def exists(key: str) -> bool:
        try:
            s3.head_object(Bucket=p.bucket, Key=key)
        except Exception:
            return False
        return True

    if exists(f"{base}/zarr.json"):
        return True
    if exists(f"{base}/.zarray"):
        return False
    return None


def open_full_res(url: str = DEFAULT_REF.link, *, v3: bool | None = None, verbose: bool = True) -> TSArrayReader:
    """Open the full-res array at `url` anonymously. Format is detected from metadata (`v3=None`) and tried
    first; pass `v3=True/False` to force it. Falls back to probing level-0-vs-tile x v3-vs-v2."""
    store = S3Store(region=REGION)
    array_url = f"{url}/{LEVEL}"
    if v3 is None:
        v3 = _detect_v3(array_url)
    attempts = ([(array_url, v3)] if v3 is not None else []) + [
        (array_url, True),
        (array_url, False),
        (url, True),
        (url, False),
    ]
    seen: set[tuple[str, bool]] = set()
    for path, use_v3 in attempts:
        if (path, use_v3) in seen:
            continue
        seen.add((path, use_v3))
        try:
            reader = TSArrayReader(S3Path(path), store=store, anonymous=True, v3=use_v3)
            if verbose:
                console.print(f"opened [cyan]{path}[/]  (zarr v{'3' if use_v3 else '2'})  shape={reader.shape}")
            return reader
        except Exception as e:
            if verbose:
                msg = str(e).splitlines()[0][:80]
                console.print(f"  [dim]x {path} v{'3' if use_v3 else '2'}: {type(e).__name__}: {msg}[/]")
    raise SystemExit("could not open the array (tried level 0 and the tile, v3 and v2)")


def load_real_block(ref: DataRef = DEFAULT_REF, *, verbose: bool = True) -> np.ndarray:
    """Read the z-window `ref` selects into RAM as a `(n, y, x)` array; the range is clamped in-range."""
    reader = open_full_res(ref.link, v3=ref.v3, verbose=verbose)
    z, y, x = reader.shape[-3], reader.shape[-2], reader.shape[-1]
    n = ref.n
    z0 = max(0, min(ref.z_start, z - n))
    if verbose:
        console.print(f"reading {n} frames @ z0={z0}/{z} (y={y} x={x}, ~{n * y * x * 2 / 1e9:.1f} GB)...")
    t0 = time.perf_counter()
    block = reader.read_3d(z0=z0, n=n)
    if verbose:
        gb, dt = block.nbytes / 1e9, time.perf_counter() - t0
        console.print(
            f"read {block.shape} {block.dtype} = {gb:.2f} GB in {dt:.1f}s -> {gb / dt * 1000:.0f} MB/s "
            f"| min={int(block.min())} max={int(block.max())} mean={float(block.mean()):.1f}"
        )
    return block


if __name__ == "__main__":
    load_real_block()
