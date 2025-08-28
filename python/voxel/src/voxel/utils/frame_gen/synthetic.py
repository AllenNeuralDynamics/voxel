import numpy as np

from .base import FrameGenerator


class RippleGenerator(FrameGenerator):
    """Generates frames with a concentric ripple pattern."""

    def __init__(
        self,
        height_px: int,
        width_px: int,
        data_type: np.dtype,
        ring_count: int = 20,
        duty_cycle: float = 0.5,
    ):
        self.height = height_px
        self.width = width_px
        self.dtype = data_type
        self.ring_count = ring_count
        self.duty_cycle = duty_cycle

    def generate(self, nframes: int = 1) -> np.ndarray:
        """Generates a static ripple frame and broadcasts it."""
        max_val = np.iinfo(self.dtype).max
        max_radius = min(self.width, self.height) / 2.0
        ring_thickness = max_radius / self.ring_count
        crest_width = ring_thickness * self.duty_cycle

        y_indices = np.arange(self.height) - self.height / 2
        x_indices = np.arange(self.width) - self.width / 2
        xv, yv = np.meshgrid(x_indices, y_indices)
        distance = np.sqrt(xv**2 + yv**2)
        ring_mod = distance % ring_thickness

        frame = np.where(ring_mod < crest_width, 0, max_val).astype(self.dtype)
        return np.broadcast_to(frame, (nframes, self.height, self.width))


# -----------------------------------------------------------------------------


class SpiralGenerator(FrameGenerator):
    """Generates frames with a spiral pattern."""

    def __init__(self, height_px: int, width_px: int, data_type: np.dtype | None = None, tile_size: int = 10):
        data_type = data_type if data_type else np.dtype(np.uint16)
        self.height = height_px
        self.width = width_px
        self.dtype = data_type
        self.tile_size = tile_size
        self.z_pos = 0

    def generate(self, nframes: int = 1) -> np.ndarray:
        """Generates a stack of frames with an expanding spiral pattern.

        Note: This generator is stateful. Each call to generate continues
        the pattern from where it left off.
        """
        y_indices = np.arange(self.height) - self.height // 2
        x_indices = np.arange(self.width) - self.width // 2
        xv, yv = np.meshgrid(x_indices, y_indices)

        distance = np.sqrt(xv**2 + yv**2)
        max_val = np.iinfo(self.dtype).max

        frames = np.zeros((nframes, self.height, self.width), dtype=self.dtype)

        for i in range(nframes):
            # The pattern changes with each frame in the batch
            current_distance_offset = self.z_pos * (self.tile_size / 2.0)
            pattern = ((distance + current_distance_offset) // self.tile_size) % 2
            frames[i] = pattern * max_val
            self.z_pos += 1

        return frames


# -----------------------------------------------------------------------------


class CheckeredGenerator(FrameGenerator):
    """Generates frames with a dynamic checkered pattern using only NumPy."""

    def __init__(
        self,
        height_px: int,
        width_px: int,
        initial_size: int = 2,
        final_size: int = 20,
        data_type: np.dtype | None = None,
    ):
        self.height = height_px
        self.width = width_px
        self.dtype = data_type if data_type else np.dtype(np.uint16)
        self.initial_size = initial_size
        self.final_size = min(width_px // 10, final_size)
        self.z_idx = 0

        # Precompute static indices
        self._y, self._x = np.indices((self.height, self.width))

    def generate(self, nframes: int = 1) -> np.ndarray:
        frames = np.zeros((nframes, self.height, self.width), dtype=self.dtype)
        max_val = np.iinfo(self.dtype).max

        # Calculate all checker sizes for the batch
        t = np.linspace(0, 1, num=nframes, retstep=False)
        checker_sizes = self.initial_size + (self.final_size - self.initial_size) * t
        checker_sizes = np.maximum(1, np.round(checker_sizes)).astype(np.int32)

        start_z = self.z_idx * nframes

        # Loop through each frame since checker_size changes
        for i in range(nframes):
            checker_size = checker_sizes[i]
            z_pos = start_z + i

            pattern = ((self._x // checker_size) + (self._y // checker_size) + z_pos) % 2

            frames[i] = pattern * max_val

        self.z_idx += 1
        return frames
