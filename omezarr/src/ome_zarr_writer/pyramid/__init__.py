import numpy as np
from ome_zarr_writer.types import ScaleLevel

from ._numpy import pyramids_2d as pyramids_2d_numpy
from ._numpy import pyramids_3d as pyramids_3d_numpy


def pyramids_2d(volume: np.ndarray, max_level: ScaleLevel) -> dict[ScaleLevel, np.ndarray]:
    try:
        from ._numba import pyramids_2d as pyramids_2d_numba

        return pyramids_2d_numba(volume, max_level)
    except ImportError:
        return pyramids_2d_numpy(volume, max_level)


def pyramids_3d(volume: np.ndarray, max_level: ScaleLevel) -> dict[ScaleLevel, np.ndarray]:
    try:
        from ._numba import pyramids_3d as pyramids_3d_numba

        return pyramids_3d_numba(volume, max_level)
    except ImportError:
        return pyramids_3d_numpy(volume, max_level)
