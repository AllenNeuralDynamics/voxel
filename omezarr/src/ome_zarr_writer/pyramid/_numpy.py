"""NumPy-based implementation of multi-scale pyramid generation."""

import math

import numpy as np

from ome_zarr_writer.types import ScaleLevel


def _downsample_2x(img: np.ndarray) -> np.ndarray:
    """Downsample 2D image by 2x using box averaging."""
    H, W = img.shape
    H2, W2 = (H // 2) * 2, (W // 2) * 2
    if H2 == 0 or W2 == 0:
        return img
    return img[:H2, :W2].reshape(H2 // 2, 2, W2 // 2, 2).mean(axis=(1, 3))


def pyramids_3d(block: np.ndarray, max_level: ScaleLevel) -> dict[ScaleLevel, np.ndarray]:
    """Compute 3D multi-scale pyramid via chained 2×2×2 means."""
    results: dict[ScaleLevel, np.ndarray] = {}

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
            # current_vol = current_vol[:T2, :H2, :W2].reshape(T2 // 2, 2, H2 // 2, 2, W2 // 2, 2).mean(axis=(1, 3, 5))
            current_vol = current_vol[:T2, :H2, :W2].reshape(T2 // 2, 2, H2 // 2, 2, W2 // 2, 2).max(axis=(1, 3, 5))
            current_factor *= 2

        t_out = block.shape[0] // target_factor
        h_out = block.shape[1] // target_factor
        w_out = block.shape[2] // target_factor
        results[target_level] = current_vol[:t_out, :h_out, :w_out]

    return results


def pyramids_2d(img: np.ndarray, max_level: ScaleLevel) -> dict[ScaleLevel, np.ndarray]:
    """Compute 2D multi-scale pyramid using chained 2x2 means."""
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
