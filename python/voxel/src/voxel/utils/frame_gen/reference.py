from abc import abstractmethod
from pathlib import Path
import numpy as np
import tifffile
from skimage.transform import resize as skimage_resize

from .base import FrameGenerator


class BaseReferenceGenerator(FrameGenerator):
    """
    An abstract base class for reference image generators.
    Handles caching, noise, and the overall generation algorithm.
    """

    def __init__(
        self,
        height_px: int,
        width_px: int,
        data_type: np.dtype = np.dtype(np.uint16),
        path: str | None = None,
        apply_noise: bool = True,
    ):
        self.height = height_px
        self.width = width_px
        self.dtype = data_type
        self.path = path or str(Path(__file__).parent / "default_reference.tif")
        self.apply_noise = apply_noise
        self._processed_base_image = None  # For caching

    @abstractmethod
    def _resize_image(self, image: np.ndarray) -> np.ndarray:
        """
        Abstract method for resizing. Subclasses must implement this.
        """
        raise NotImplementedError

    def generate(self, nframes: int = 1) -> np.ndarray:
        # This is the "template method". It defines the skeleton.
        if self._processed_base_image is None:
            image = tifffile.imread(self.path).astype(np.float32)

            if self.apply_noise:
                photons = np.random.poisson(image)
                image = (photons * 0.85 * 0.08).astype(np.float32)

            # Call the specific implementation from the subclass
            self._processed_base_image = self._resize_image(image)

        frame_batch = np.broadcast_to(self._processed_base_image, (nframes, self.height, self.width))
        return frame_batch.astype(self.dtype)


class UpsampleReferenceGenerator(BaseReferenceGenerator):
    """Generates a frame by upsampling/resizing the reference image."""

    def _resize_image(self, image: np.ndarray) -> np.ndarray:
        return np.array(
            skimage_resize(
                image,
                output_shape=(self.height, self.width),
                order=1,
                preserve_range=True,
                anti_aliasing=False,
            )
        )


class TileReferenceGenerator(BaseReferenceGenerator):
    """Generates a frame by tiling the reference image."""

    def _resize_image(self, image: np.ndarray) -> np.ndarray:
        tiles_y = (self.height + image.shape[0] - 1) // image.shape[0]
        tiles_x = (self.width + image.shape[1] - 1) // image.shape[1]
        tiled_image = np.tile(image, (tiles_y, tiles_x))
        return tiled_image[: self.height, : self.width]


class ReferenceGenerator(FrameGenerator):
    """
    Generates frames from a reference TIFF image using only NumPy and Scikit-image.
    This version is NOT dependent on JAX.
    """

    def __init__(
        self,
        height_px: int,
        width_px: int,
        data_type: np.dtype,
        path: str,
        use_tile: bool = False,
        apply_noise: bool = True,
    ):
        self.height = height_px
        self.width = width_px
        self.dtype = data_type
        self.path = path
        self.use_tile = use_tile
        self.apply_noise = apply_noise
        self._processed_base_image = None  # For caching

    def generate(self, nframes: int = 1) -> np.ndarray:
        # 1. Process the base image only on the first run
        if self._processed_base_image is None:
            image = tifffile.imread(self.path).astype(np.float32)

            if self.apply_noise:
                # Use NumPy for the noise model
                photons = np.random.poisson(image)
                image = (photons * 0.85 * 0.08).astype(np.float32)

            # Use scikit-image for resizing
            resized = skimage_resize(
                image,
                output_shape=(self.height, self.width),
                order=1,  # 1 = bilinear interpolation, same as JAX's 'linear'
                preserve_range=True,  # Crucial to prevent rescaling to [0, 1]
                anti_aliasing=False,
            )
            self._processed_base_image = resized

        # 2. Broadcast the cached image to the desired frame count using NumPy
        base_image = np.array(self._processed_base_image, dtype=self.dtype)
        frame_batch = np.broadcast_to(base_image, (nframes, self.height, self.width))
        return frame_batch.astype(self.dtype)


class ReferenceGenerator2(FrameGenerator):
    def __init__(
        self,
        height_px: int,
        width_px: int,
        data_type: np.dtype,
        path: str,
        use_tile: bool = False,
        apply_noise: bool = True,
    ):
        self.height = height_px
        self.width = width_px
        self.dtype = data_type
        self.path = path
        self.use_tile = use_tile
        self.apply_noise = apply_noise
        self._processed_base_image = None  # For caching

    def _load_dependencies(self):
        """Lazily imports heavy modules."""
        global jnp, random, resize, tifffile
        import jax.numpy as jnp
        import tifffile
        from jax import random
        from jax.image import resize

    def generate(self, nframes: int = 1) -> np.ndarray:
        # 1. Lazy load and process the base image only on the first run
        if self._processed_base_image is None:
            self._load_dependencies()

            image = tifffile.imread(self.path).astype(np.float32)

            if self.apply_noise:
                # Simplified noise model for brevity
                key = random.PRNGKey(42)
                photons = random.poisson(key, image)
                image = (photons * 0.85 * 0.08).astype(np.float32)

            resized = resize(jnp.array(image), (self.height, self.width), method="linear")
            self._processed_base_image = resized

        # 2. Broadcast the cached image to the desired frame count
        frame_batch = jnp.broadcast_to(self._processed_base_image, (nframes, self.height, self.width))
        return np.array(frame_batch, dtype=self.dtype)
