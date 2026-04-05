import logging
import os
from collections.abc import Callable

import numpy as np

from ome_zarr_writer.types import ScaleLevel

from ._numpy import pyramids_2d as pyramids_2d_numpy
from ._numpy import pyramids_3d as pyramids_3d_numpy

log = logging.getLogger(__name__)


pyramids_2d: Callable[[np.ndarray, ScaleLevel], dict[ScaleLevel, np.ndarray]] = pyramids_2d_numpy
pyramids_3d: Callable[[np.ndarray, ScaleLevel], dict[ScaleLevel, np.ndarray]] = pyramids_3d_numpy

# Determine if numba's parallel features are safe to use.
# The default 'workqueue' threading layer is NOT thread-safe for concurrent access
# (e.g., multiple ring buffer slots downscaling in parallel).
# TBB is thread-safe but only available on Linux via pip (no macOS ARM64 wheels).
# On macOS, TBB can be installed via brew but numba needs the Python tbb package.
try:
    os.environ.setdefault("NUMBA_THREADING_LAYER", "tbb")
    # Verify numba can actually launch its threading layer.
    # This triggers JIT compilation of a trivial parallel function, which will
    # raise ValueError if no thread-safe backend (TBB) is available.
    from numba import jit, prange

    from ._numba import pyramids_2d as _pyramids_2d_numba
    from ._numba import pyramids_3d as _pyramids_3d_numba

    @jit(nopython=True, parallel=True, cache=False)
    def _test_threading():
        s = 0
        for i in prange(4):
            s += i
        return s

    _test_threading()

    pyramids_2d = _pyramids_2d_numba
    pyramids_3d = _pyramids_3d_numba
    log.warning("Using numba (TBB) for pyramid downscaling")
except Exception:
    log.warning("Using numpy for pyramid downscaling (numba TBB not available)")
