"""Numba JIT-compiled CPU implementation of multi-scale pyramid generation."""

import math
import numpy as np
from ome_zarr_writer.types import ScaleLevel

try:
    from numba import jit, prange

    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False

    # Dummy decorators for type checking
    def jit(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def prange(*args, **kwargs):
        return range(*args, **kwargs)


if NUMBA_AVAILABLE:

    @jit(nopython=True, parallel=True, fastmath=True, cache=True)
    def _downsample_2x_kernel(img: np.ndarray, out: np.ndarray) -> None:
        """Numba-accelerated 2x2 box averaging kernel."""
        H_out, W_out = out.shape
        for i in prange(H_out):
            for j in range(W_out):
                i2 = i * 2
                j2 = j * 2
                out[i, j] = (img[i2, j2] + img[i2, j2 + 1] + img[i2 + 1, j2] + img[i2 + 1, j2 + 1]) * 0.25

    @jit(nopython=True, parallel=True, fastmath=True, cache=True)
    def _downsample_3d_kernel(vol: np.ndarray, out: np.ndarray) -> None:
        """Numba-accelerated 2x2x2 box averaging kernel."""
        T_out, H_out, W_out = out.shape
        for t in prange(T_out):
            for i in range(H_out):
                for j in range(W_out):
                    t2, i2, j2 = t * 2, i * 2, j * 2
                    s = 0.0
                    for dt in range(2):
                        for di in range(2):
                            for dj in range(2):
                                s += vol[t2 + dt, i2 + di, j2 + dj]
                    out[t, i, j] = s * 0.125


def _downsample_2x(img: np.ndarray) -> np.ndarray:
    """Downsample 2D image by 2x using Numba JIT kernel."""
    if not NUMBA_AVAILABLE:
        raise ImportError("Numba not available. Install with: pip install numba")

    H, W = img.shape
    H2, W2 = (H // 2) * 2, (W // 2) * 2
    if H2 == 0 or W2 == 0:
        return img

    img_cropped = img[:H2, :W2]
    out = np.empty((H2 // 2, W2 // 2), dtype=np.float32)
    img_f32 = img_cropped.astype(np.float32)
    _downsample_2x_kernel(img_f32, out)
    return out


def pyramids_3d(block: np.ndarray, max_level: ScaleLevel) -> dict[ScaleLevel, np.ndarray]:
    """Compute 3D multi-scale pyramid using Numba-accelerated kernels."""
    if not NUMBA_AVAILABLE:
        raise ImportError("Numba not available. Install with: pip install numba")

    results = {}
    levels = [level for level in max_level.levels if level != ScaleLevel.L0]
    sorted_levels = sorted(levels, key=lambda x: x.factor)

    current_factor = 1
    current_vol = block.astype(np.float32, copy=False)

    for target_level in sorted_levels:
        target_factor = target_level.factor
        steps_needed = int(math.log2(target_factor)) - int(math.log2(current_factor))

        for _ in range(steps_needed):
            T, H, W = current_vol.shape
            T2, H2, W2 = (T // 2) * 2, (H // 2) * 2, (W // 2) * 2
            if min(T2, H2, W2) == 0:
                break
            out = np.empty((T2 // 2, H2 // 2, W2 // 2), dtype=np.float32)
            _downsample_3d_kernel(current_vol[:T2, :H2, :W2], out)
            current_vol = out
            current_factor *= 2

        t_out = block.shape[0] // target_factor
        h_out = block.shape[1] // target_factor
        w_out = block.shape[2] // target_factor
        results[target_level] = current_vol[:t_out, :h_out, :w_out]

    return results


def pyramids_2d(img: np.ndarray, max_level: ScaleLevel) -> dict[ScaleLevel, np.ndarray]:
    """Compute 2D multi-scale pyramid using Numba-accelerated operations."""
    if not NUMBA_AVAILABLE:
        raise ImportError("Numba not available. Install with: pip install numba")

    results = {}
    levels = [level for level in max_level.levels if level != ScaleLevel.L0]
    sorted_levels = sorted(levels, key=lambda x: x.factor)

    current_factor = 1
    current_img = img.astype(np.float32, copy=False)

    for target_level in sorted_levels:
        target_factor = target_level.factor
        steps_needed = int(math.log2(target_factor)) - int(math.log2(current_factor))

        for _ in range(steps_needed):
            current_img = _downsample_2x(current_img)
            current_factor *= 2

        target_h = img.shape[0] // target_factor
        target_w = img.shape[1] // target_factor
        results[target_level] = current_img[:target_h, :target_w]

    return results
