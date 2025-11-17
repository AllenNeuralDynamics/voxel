from enum import Enum, auto
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


class ResizeMode(Enum):
    """Strategy for resizing reference image to target dimensions."""

    AUTO = auto()  # Automatically choose fastest method
    TILE = auto()  # Tile the reference image
    UPSAMPLE = auto()  # Resize using interpolation


class ReferenceFrameGenerator:
    """Generates mock camera frames from a reference image.

    Automatically selects the most efficient strategy (tiling vs upsampling)
    based on target size relative to reference image size.
    """

    def __init__(
        self,
        height_px: int,
        width_px: int,
        data_type: np.dtype | None = None,
        path: str | None = None,
        apply_noise: bool = True,
        mode: ResizeMode = ResizeMode.AUTO,
        intensity_scale: float = 0.5,  # 0.08
    ):
        """Initialize frame generator.

        Args:
            height_px: Target frame height in pixels
            width_px: Target frame width in pixels
            data_type: Output data type (defaults to uint16)
            path: Path to reference image (defaults to bundled image)
            apply_noise: Apply Poisson noise simulation
            mode: Resize strategy (AUTO chooses based on size ratio)
            intensity_scale: Scale factor for intensity (0.0-1.0), simulates detector gain
        """
        self.height = height_px
        self.width = width_px
        self.dtype = data_type if data_type is not None else np.dtype(np.uint16)
        self.path = path or str(Path(__file__).parent / "default_reference.png")
        self.apply_noise = apply_noise
        self.mode = mode
        self.intensity_scale = intensity_scale
        self._processed_base_image: np.ndarray | None = None

    def _load_image(self, path: str) -> np.ndarray:
        """Load image from disk. Handles various formats via Pillow."""
        img = Image.open(path)
        arr = np.array(img)
        # Ensure 2D grayscale
        if arr.ndim == 3:
            arr = arr[:, :, 0]  # Take first channel if RGB
        return arr.astype(np.float32)

    def _should_tile(self, ref_shape: tuple[int, int]) -> bool:
        """Determine if tiling is more efficient than upsampling.

        Tiling is faster when target is larger than reference and
        is a good integer multiple of reference dimensions.
        """
        ref_h, ref_w = ref_shape
        # Tile if target is at least 2x larger in both dimensions
        return self.height >= ref_h * 2 and self.width >= ref_w * 2

    def _tile_image(self, image: np.ndarray) -> np.ndarray:
        """Generate frame by tiling reference image."""
        tiles_y = (self.height + image.shape[0] - 1) // image.shape[0]
        tiles_x = (self.width + image.shape[1] - 1) // image.shape[1]
        tiled_image = np.tile(image, (tiles_y, tiles_x))
        return tiled_image[: self.height, : self.width]

    def _upsample_image(self, image: np.ndarray) -> np.ndarray:
        """Generate frame by upsampling reference image."""
        return cv2.resize(image, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

    def _resize_image(self, image: np.ndarray) -> np.ndarray:
        """Resize image using selected or automatic strategy."""
        if self.mode == ResizeMode.TILE:
            return self._tile_image(image)
        elif self.mode == ResizeMode.UPSAMPLE:
            return self._upsample_image(image)
        else:  # AUTO
            if self._should_tile(image.shape):
                return self._tile_image(image)
            else:
                return self._upsample_image(image)

    def generate(self, nframes: int = 1) -> np.ndarray:
        """Generate batch of frames.

        Args:
            nframes: Number of frames to generate

        Returns:
            Array of shape (nframes, height, width) with dtype self.dtype
        """
        if self._processed_base_image is None:
            image = self._load_image(self.path)

            if self.apply_noise:
                rng = np.random.default_rng()
                photons = rng.poisson(image)
                image = (photons * 0.85 * self.intensity_scale).astype(np.float32)

            self._processed_base_image = self._resize_image(image)

        frame_batch = np.broadcast_to(self._processed_base_image, (nframes, self.height, self.width))
        return frame_batch.astype(self.dtype)

    def __iter__(self):
        """Allows the generator to be used in a loop, yielding single frames."""
        return self

    def __next__(self) -> np.ndarray:
        """Generate next frame."""
        return self.generate(nframes=1)[0]
