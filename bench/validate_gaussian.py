"""Independent correctness oracle for the separable gaussian downscale.

The unit tests check numba==numpy (self-consistency) plus analytic properties (impulse, linear ramp).
This adds the heavyweight cross-check: the SAME operator computed a completely different way — scipy's
compiled N-D correlation followed by decimation — and compares it to `pyramids_3d_numba`. Agreement to
float precision means our streaming/rolling separable implementation computes the intended filter, not
just something self-consistent.

scipy isn't a project dependency (it's only needed here) and can't be a PEP 723 inline dep — the script
imports the workspace `ome-zarr-writer`, which an isolated script env can't resolve — so pull scipy in
with uv's ephemeral overlay, which keeps the project env intact:

    uv run --with scipy bench/validate_gaussian.py

Exits non-zero if any check fails.
"""

import sys

import numpy as np
from ome_zarr_writer.dataset import DownscaleType, ScaleLevel
from ome_zarr_writer.pyramid import pyramids_3d_numba

try:
    from scipy.ndimage import correlate1d  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:
    sys.exit(
        "scipy is required for this script but isn't a project dependency.\n"
        "Re-run with uv's ephemeral overlay (keeps the workspace env intact):\n\n"
        "    uv run --with scipy bench/validate_gaussian.py\n"
    )

_K = np.array([1.0, 3.0, 3.0, 1.0])  # binomial taps; /8 per axis folded into the final /512


def ref_step(vol: np.ndarray) -> np.ndarray:
    """One 2x gaussian downscale via scipy: full-resolution separable correlation with edge replication
    (`mode='nearest'` == our index clamp), then decimate. scipy centres a length-4 filter at index 2, so
    output p reads inputs p-2..p+1; sampling odd positions (`[1::2]`) makes output i read inputs
    2i-1..2i+2 — exactly our taps. Truncates to even extents first, matching the writer's orchestration."""
    z2, y2, x2 = (vol.shape[0] // 2) * 2, (vol.shape[1] // 2) * 2, (vol.shape[2] // 2) * 2
    v = vol[:z2, :y2, :x2].astype(np.float64)
    for axis in (0, 1, 2):
        v = correlate1d(v, _K, axis=axis, mode="nearest")
    return (v[1::2, 1::2, 1::2] / 512.0).astype(np.float32)


def _tap_weight(a: int, o: int, n: int) -> float:
    taps = (max(2 * o - 1, 0), 2 * o, min(2 * o + 1, n - 1), min(2 * o + 2, n - 1))
    return sum(w for t, w in zip(taps, (1.0, 3.0, 3.0, 1.0), strict=True) if t == a)


def check(name: str, a: np.ndarray, b: np.ndarray, *, rtol: float = 1e-5, atol: float = 1e-3) -> bool:
    ok = a.shape == b.shape and np.allclose(a, b, rtol=rtol, atol=atol)
    diff = float(np.abs(a.astype(np.float64) - b.astype(np.float64)).max()) if a.shape == b.shape else float("nan")
    print(f"  [{'ok' if ok else 'FAIL'}] {name:34s} shapes {a.shape} vs {b.shape}  max_abs_diff={diff:.3e}")
    return ok


def main() -> int:
    ok = True

    # 1) Anchor: the scipy reference must reproduce the analytic impulse response (pure spec). This
    #    justifies the [1::2] alignment independently of our code, so it's a valid oracle below.
    z, y, x = 16, 16, 16
    az, ay, ax = 7, 8, 6
    imp = np.zeros((z, y, x), dtype=np.float32)
    imp[az, ay, ax] = 1000.0
    zo, yo, xo = z // 2, y // 2, x // 2
    analytic = np.zeros((zo, yo, xo), dtype=np.float64)
    for k in range(zo):
        for j in range(yo):
            for i in range(xo):
                analytic[k, j, i] = 1000.0 * _tap_weight(az, k, z) * _tap_weight(ay, j, y) * _tap_weight(ax, i, x) / 512
    print("anchor scipy reference to the analytic impulse (spec):")
    ok &= check("scipy ref == analytic impulse", ref_step(imp), analytic)

    # 2) Oracle: our numba gaussian vs the scipy reference, on random data, single + chained steps.
    print("\nnumba separable gaussian vs scipy N-D convolution oracle:")
    for seed, shape in ((0, (24, 30, 26)), (1, (33, 17, 41)), (2, (64, 48, 50))):  # incl odd extents
        blk = np.random.default_rng(seed).integers(0, 700, size=shape, dtype=np.uint16)
        ours = pyramids_3d_numba(blk, ScaleLevel.L2, reduction=DownscaleType.GAUSSIAN, parallel=True)
        r1 = ref_step(blk)
        r2 = ref_step(r1)  # chained step validates the multi-level orchestration
        ok &= check(f"L1 seed={seed} {shape}", ours[ScaleLevel.L1], r1)
        ok &= check(f"L2 seed={seed} {shape}", ours[ScaleLevel.L2], r2)

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
