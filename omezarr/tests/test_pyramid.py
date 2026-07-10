"""Pyramid reductions: numba and numpy agree, gaussian is a normalized/grid-aligned anti-aliaser,
and every `DownscaleType` the metadata can declare has a matching kernel (so the on-disk `type` label
can never name a reduction the writer doesn't actually compute).
"""

import numpy as np
import pytest

from ome_zarr_writer.dataset import DownscaleType, ScaleLevel
from ome_zarr_writer.pyramid import _KERNELS, _SUPPORTED_REDUCTIONS, pyramids_3d_numba, pyramids_3d_numpy

_MAX_LEVEL = ScaleLevel.L2


def _expected_shape(block: np.ndarray, level: ScaleLevel) -> tuple[int, int, int]:
    return tuple(dim // level.factor for dim in block.shape)  # type: ignore[return-value]


def _block() -> np.ndarray:
    # Odd-ish extents (10, 12 not powers of two) exercise the even-truncation + edge-clamp paths.
    return np.random.default_rng(0).integers(0, 1000, size=(8, 10, 12), dtype=np.uint16)


def test_every_downscale_type_is_supported() -> None:
    """The merge of `Reduction` into `DownscaleType`: every declarable metadata value is handled by the
    step dispatcher, so the writer can pass `config.downscale_type` straight through with no translation
    table and the on-disk `type` can never name a reduction we don't compute."""
    assert _SUPPORTED_REDUCTIONS == set(DownscaleType)
    # Block reductions (all but gaussian, which is separable) have a (vol, out) kernel per specialization.
    for dt in set(DownscaleType) - {DownscaleType.GAUSSIAN}:
        assert (dt, False) in _KERNELS and (dt, True) in _KERNELS, dt


def test_numpy_reductions_shapes_and_gaussian_normalized() -> None:
    block = _block()
    for dt in DownscaleType:
        pyr = pyramids_3d_numpy(block, _MAX_LEVEL, reduction=dt)
        for level, vol in pyr.items():
            assert vol.shape == _expected_shape(block, level), (dt, level)
            assert vol.dtype == np.float32

    # A separable binomial with normalized weights must leave a constant field unchanged.
    const = np.full((8, 8, 8), 137.0, dtype=np.float32)
    g = pyramids_3d_numpy(const, ScaleLevel.L1, reduction=DownscaleType.GAUSSIAN)
    assert np.allclose(g[ScaleLevel.L1], 137.0)


def test_gaussian_grid_aligned_with_mean() -> None:
    """Gaussian must land on the same output grid as mean (its taps are centred on the same 2-block),
    so pyramid level shapes are identical regardless of the chosen reduction."""
    block = _block()
    mean = pyramids_3d_numpy(block, _MAX_LEVEL, reduction=DownscaleType.MEAN)
    gauss = pyramids_3d_numpy(block, _MAX_LEVEL, reduction=DownscaleType.GAUSSIAN)
    assert {lvl: v.shape for lvl, v in mean.items()} == {lvl: v.shape for lvl, v in gauss.items()}


@pytest.mark.slow  # first call JIT-compiles the kernels
def test_numba_matches_numpy_reference() -> None:
    block = _block()
    for dt in DownscaleType:
        nb = pyramids_3d_numba(block, _MAX_LEVEL, reduction=dt, parallel=False)
        ref = pyramids_3d_numpy(block, _MAX_LEVEL, reduction=dt)
        assert nb.keys() == ref.keys()
        for level in nb:
            assert nb[level].shape == ref[level].shape == _expected_shape(block, level), (dt, level)
            # exact for min/max, within fp rounding for mean/gaussian
            assert np.allclose(nb[level], ref[level], rtol=1e-5, atol=1e-4), (dt, level)


# ---------------------------------------------------------------------------
# Gaussian correctness against independent ground truth (not just numba==numpy,
# which is self-consistency). These run on the fast numpy path; `test_numba_matches_
# numpy_reference` ties the numba kernels to it, so validating one validates both.
# `bench/validate_gaussian.py` adds a scipy N-D convolution oracle on top.
# ---------------------------------------------------------------------------


def _gauss_l1(block: np.ndarray) -> np.ndarray:
    return pyramids_3d_numpy(block, ScaleLevel.L1, reduction=DownscaleType.GAUSSIAN)[ScaleLevel.L1]


def _tap_weight(a: int, o: int, n: int) -> float:
    """Weight the separable binomial gives input index `a` at output `o` along one axis of length `n`,
    derived from the SPEC (taps 2o-1..2o+2, weights 1,3,3,1, edge-clamped) — not from the implementation.
    Sums contributions so a clamped edge index that appears in multiple taps is counted correctly."""
    taps = (max(2 * o - 1, 0), 2 * o, min(2 * o + 1, n - 1), min(2 * o + 2, n - 1))
    weights = (1.0, 3.0, 3.0, 1.0)
    return sum(w for t, w in zip(taps, weights, strict=True) if t == a)


def test_gaussian_impulse_response() -> None:
    """A single impulse must produce exactly the separable [1,3,3,1]/8 footprint at the hand-derived
    output positions — pins the kernel shape, weights, centring, and /512 normalization at once."""
    z, y, x = 16, 16, 16
    az, ay, ax, amp = 7, 8, 6, 1000.0  # interior impulse (no edge clamp)
    block = np.zeros((z, y, x), dtype=np.float32)
    block[az, ay, ax] = amp
    out = _gauss_l1(block)

    zo, yo, xo = z // 2, y // 2, x // 2
    expected = np.zeros((zo, yo, xo), dtype=np.float64)
    for k in range(zo):
        for j in range(yo):
            for i in range(xo):
                expected[k, j, i] = amp * _tap_weight(az, k, z) * _tap_weight(ay, j, y) * _tap_weight(ax, i, x) / 512.0
    assert np.allclose(out, expected, atol=1e-3), float(np.abs(out - expected).max())


def test_gaussian_reproduces_linear_ramp() -> None:
    """A symmetric normalized filter reproduces a linear field sampled at each output's centre of mass
    (2i+0.5 per axis). Independently confirms centring and unit DC gain. Interior only (edges clamp)."""
    z, y, x = 16, 18, 20
    zz, yy, xx = np.meshgrid(np.arange(z), np.arange(y), np.arange(x), indexing="ij")
    cz, cy, cx, c0 = 0.5, 3.0, 2.0, 5.0
    block = (cz * zz + cy * yy + cx * xx + c0).astype(np.float32)
    out = _gauss_l1(block)

    zo, yo, xo = z // 2, y // 2, x // 2
    ks, js, iss = np.meshgrid(np.arange(zo), np.arange(yo), np.arange(xo), indexing="ij")
    expected = cz * (2 * ks + 0.5) + cy * (2 * js + 0.5) + cx * (2 * iss + 0.5) + c0
    inner = (slice(1, -1), slice(1, -1), slice(1, -1))
    assert np.allclose(out[inner], expected[inner], rtol=1e-4, atol=1e-2), float(
        np.abs(out[inner] - expected[inner]).max()
    )


def test_gaussian_output_is_bounded() -> None:
    """Positive weights summing to 1 → each output is a convex combination of its inputs, so the output
    range can't exceed the input range (rules out sign/normalization errors)."""
    block = np.random.default_rng(3).integers(0, 4000, size=(12, 14, 16), dtype=np.uint16)
    out = _gauss_l1(block)
    assert out.min() >= float(block.min()) - 1e-3
    assert out.max() <= float(block.max()) + 1e-3


def test_gaussian_transpose_equivariant() -> None:
    """Identical kernel on every axis → downscaling commutes with axis permutation. Catches any X/Y/Z
    mix-up (a bug numba==numpy would share and miss). Distinct extents make a swap observable."""
    block = np.random.default_rng(4).integers(0, 2000, size=(12, 16, 20), dtype=np.uint16)
    perm = (2, 0, 1)
    a = _gauss_l1(block).transpose(perm)
    b = _gauss_l1(np.ascontiguousarray(block.transpose(perm)))
    assert a.shape == b.shape
    assert np.allclose(a, b, rtol=1e-5, atol=1e-4), float(np.abs(a - b).max())
