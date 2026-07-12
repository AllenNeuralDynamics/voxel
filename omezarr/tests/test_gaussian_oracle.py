"""Independent correctness oracle for the separable gaussian downscale.

`test_pyramid.py` checks numba==numpy (self-consistency) plus analytic properties. This adds the
heavyweight cross-check: the SAME operator computed a completely different way -- scipy's compiled N-D
correlation followed by decimation -- compared to `pyramids_3d_numba`. Agreement to float precision means
the streaming/rolling separable implementation computes the intended filter, not just something
self-consistent.

scipy is not a project dependency (only needed here), so these tests skip unless it is installed. Run them
with uv's ephemeral overlay, which keeps the workspace env intact:

    uv run --with scipy pytest omezarr/tests/test_gaussian_oracle.py -m slow
"""

import numpy as np
import pytest

from ome_zarr_writer.dataset import DownscaleType, ScaleLevel
from ome_zarr_writer.pyramid import pyramids_3d_numba

correlate1d = pytest.importorskip("scipy.ndimage").correlate1d  # skips the module if scipy is absent

pytestmark = pytest.mark.slow  # heavyweight (scipy N-D convolution + JIT); excluded from the fast suite

_K = np.array([1.0, 3.0, 3.0, 1.0])  # binomial taps; /8 per axis folded into the final /512


def ref_step(vol: np.ndarray) -> np.ndarray:
    """One 2x gaussian downscale via scipy: full-resolution separable correlation with edge replication
    (`mode='nearest'` == our index clamp), then decimate. scipy centres a length-4 filter at index 2, so
    output p reads inputs p-2..p+1; sampling odd positions (`[1::2]`) makes output i read inputs
    2i-1..2i+2 -- exactly our taps. Truncates to even extents first, matching the writer's orchestration."""
    z2, y2, x2 = (vol.shape[0] // 2) * 2, (vol.shape[1] // 2) * 2, (vol.shape[2] // 2) * 2
    v = vol[:z2, :y2, :x2].astype(np.float64)
    for axis in (0, 1, 2):
        v = correlate1d(v, _K, axis=axis, mode="nearest")
    return (v[1::2, 1::2, 1::2] / 512.0).astype(np.float32)


def _tap_weight(a: int, o: int, n: int) -> float:
    taps = (max(2 * o - 1, 0), 2 * o, min(2 * o + 1, n - 1), min(2 * o + 2, n - 1))
    return sum(w for t, w in zip(taps, (1.0, 3.0, 3.0, 1.0), strict=True) if t == a)


def test_scipy_ref_matches_analytic_impulse() -> None:
    """Anchor: the scipy reference must reproduce the analytic impulse response (pure spec). This
    justifies the [1::2] alignment independently of our code, so it's a valid oracle for the tests below."""
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
    assert np.allclose(ref_step(imp), analytic, rtol=1e-5, atol=1e-3)


@pytest.mark.parametrize(("seed", "shape"), [(0, (24, 30, 26)), (1, (33, 17, 41)), (2, (64, 48, 50))])
def test_numba_gaussian_matches_scipy_oracle(seed: int, shape: tuple[int, int, int]) -> None:
    """Our numba gaussian vs the scipy reference on random data, single and chained steps (odd extents
    included); the chained step validates the multi-level orchestration."""
    blk = np.random.default_rng(seed).integers(0, 700, size=shape, dtype=np.uint16)
    ours = pyramids_3d_numba(blk, ScaleLevel.L2, reduction=DownscaleType.GAUSSIAN, parallel=True)
    r1 = ref_step(blk)
    r2 = ref_step(r1)
    assert np.allclose(ours[ScaleLevel.L1], r1, rtol=1e-5, atol=1e-3)
    assert np.allclose(ours[ScaleLevel.L2], r2, rtol=1e-5, atol=1e-3)
