# voxel/utils/frame_gen.py

from enum import StrEnum
import logging
import os
import time

import numpy as np
import tifffile


os.environ["JAX_PLATFORM_NAME"] = "cpu"
os.environ["XLA_PYTHON_CLIENT_PREALLOCATE"] = "false"
import jax.numpy as jnp
from jax import config, jit, random
from jax.image import resize
from skimage.transform import resize as skimage_resize
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxel.utils.log import LoggerType

jax_loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict if name.startswith("jax")]
for logger in jax_loggers:
    logger.setLevel(logging.WARNING)

config.update("jax_platform_name", "cpu")

REFERENCE_IMAGE_PATH = os.path.dirname(os.path.abspath(__file__)) + "/reference_image.tif"

EXPOSURE_TIME_MS = 10


class FrameGenStrategy(StrEnum):
    TILE = "tile"
    UPSAMPLE = "upsample"
    RIPPLE = "ripple"
    CHECKERED = "checkered"
    SPIRAL = "spiral"


def process_image_batch(
    image: jnp.ndarray,
    nframes: int,
    height_px: int,
    width_px: int,
    exposure_time_ms: int,
    rng_key: jnp.ndarray,
    resize_method=FrameGenStrategy.UPSAMPLE,
    qe: float = 0.85,
    gain: float = 0.08,
    dark_noise: float = 6.89,
    baseline: float = 0.0,
    bitdepth: int = 16,
) -> jnp.ndarray:
    """
    Add noise, resize the image, and create a batch of frames.
    """

    rng_key, subkey1 = random.split(rng_key)
    rng_key, subkey2 = random.split(rng_key)

    # Scale the image by exposure time
    # image = image * exposure_time_ms / 0.1
    # image = image * exposure_time_ms / 0.1

    # Add shot noise (Poisson noise)
    photons = random.poisson(subkey1, image)

    # Convert to electrons with quantum efficiency
    electrons = qe * photons

    # Add dark noise (Gaussian noise)
    electrons += random.normal(subkey2, shape=electrons.shape) * dark_noise

    # Convert to ADU (Analog-to-Digital Units) and add baseline
    adu = electrons * gain + baseline

    # Clip to valid range
    max_adu = 2**bitdepth - 1
    adu = jnp.clip(adu, 0, max_adu)

    # Resize or tile the image to the desired dimensions
    if resize_method == "tile":
        tiles_y = (height_px + image.shape[0] - 1) // image.shape[0]
        tiles_x = (width_px + image.shape[1] - 1) // image.shape[1]
        tiled_image = jnp.tile(adu, (tiles_y, tiles_x))
        resized_image = tiled_image[:height_px, :width_px]
    else:
        # Upsample the image using linear interpolation
        resized_image = resize(
            adu,
            shape=(height_px, width_px),
            method="linear",
        )
    if nframes == 1:
        return resized_image

    # Create the batch by broadcasting the resized image
    return jnp.broadcast_to(resized_image, (nframes, height_px, width_px))


process_image_batch_jit = jit(process_image_batch, static_argnums=(1, 2, 3, 4, 5))


def resize_image(
    image: jnp.ndarray,
    height_px: int,
    width_px: int,
    resize_method=FrameGenStrategy.UPSAMPLE,
) -> jnp.ndarray:
    """
    Resize or tile the image to the desired dimensions without modifying pixel intensities
    (beyond interpolation if 'upsample' is chosen).
    """
    if resize_method == "tile":
        tiles_y = (height_px + image.shape[0] - 1) // image.shape[0]
        tiles_x = (width_px + image.shape[1] - 1) // image.shape[1]
        tiled_image = jnp.tile(image, (tiles_y, tiles_x))
        resized_image = tiled_image[:height_px, :width_px]
    else:
        # Upsample the image using linear interpolation
        resized_image = resize(
            image,
            shape=(height_px, width_px),
            method="linear",  # or "nearest" if you want nearest-neighbor
        )
    return resized_image


# JIT-compile for efficiency if desired
resize_image_jit = jit(resize_image, static_argnums=(1, 2, 3))


def load_and_normalize_tiff(reference_image_path: str, data_type: np.dtype) -> np.ndarray:
    image = tifffile.imread(reference_image_path)
    image = image.astype(np.float32)

    # Compute the min and max of the image
    img_min = image.min()
    img_max = image.max()

    # Normalize to the range [0, 1]
    normalized = (image - img_min) / (img_max - img_min + 1e-8)  # avoid division by zero

    # Scale to full range of the target dtype
    max_val = np.iinfo(data_type).max

    normalized = normalized * max_val

    # Convert back to the desired data type
    return normalized.astype(data_type)


def generate_reference_image2(
    height_px: int,
    width_px: int,
    data_type: np.dtype = np.dtype(np.uint16),
    reference_image_path: str = REFERENCE_IMAGE_PATH,
    exposure_time_ms: int = EXPOSURE_TIME_MS,
    resize_method=FrameGenStrategy.UPSAMPLE,
) -> np.ndarray:
    # Load the image and convert it to jax.numpy array
    image = load_and_normalize_tiff(reference_image_path, data_type)

    image = image * exposure_time_ms / 0.1

    rng_key = random.PRNGKey(42)  # Replace with a dynamically generated seed if needed

    image = process_image_batch_jit(
        jnp.array(image),
        nframes=1,
        height_px=height_px,
        width_px=width_px,
        rng_key=rng_key,
        exposure_time_ms=exposure_time_ms,
        resize_method=resize_method,
        bitdepth=np.iinfo(data_type).bits,
    )
    return np.array(image, dtype=data_type)


def normalize_image(image: np.ndarray, data_type: np.dtype) -> np.ndarray:
    """
    Normalize the image to the range of the target data type.
    """
    # Compute the min and max of the image
    img_min = image.min()
    img_max = image.max()

    # Normalize to the range [0, 1]
    normalized = (image - img_min) / (img_max - img_min + 1e-8)  # avoid division by zero

    # Scale to full range of the target dtype
    max_val = np.iinfo(data_type).max * img_max / (2**8 - 1) if img_max < 2**8 else np.iinfo(data_type).max

    normalized = normalized * max_val

    # Convert back to the desired data type
    return normalized.astype(data_type)


def generate_reference_image(
    height_px: int,
    width_px: int,
    data_type: np.dtype = np.dtype(np.uint16),
    resize_method=FrameGenStrategy.UPSAMPLE,
    qe: float = 0.85,
    gain: float = 0.08,
    dark_noise: float = 6.89,
    baseline: float = 0.0,
    exposure_time_ms: int = 10,
    reference_image_path: str = REFERENCE_IMAGE_PATH,
) -> np.ndarray:
    # Read TIFF into a float array and scale by exposure_time
    image = tifffile.imread(reference_image_path).astype(np.float32)

    image = image * (exposure_time_ms / 0.1)

    image = np.random.poisson(image)  # Poisson noise
    image = image * qe  # Convert to electrons with quantum efficiency
    image += np.random.normal(loc=0.0, scale=dark_noise, size=image.shape)  # Add dark noise (Gaussian)
    image = image * gain + baseline  # Convert to ADU (Analog-to-Digital Units) and add baseline
    image = np.clip(image, 0, 2 ** np.iinfo(data_type).bits - 1)  # Clip to valid range

    image = normalize_image(image, data_type)

    # 10. Resize or tile
    if resize_method == "tile":
        # Calculate how many tiles needed in each dimension
        tiles_y = (height_px + image.shape[0] - 1) // image.shape[0]
        tiles_x = (width_px + image.shape[1] - 1) // image.shape[1]
        tiled = np.tile(image, (tiles_y, tiles_x))
        resized = tiled[:height_px, :width_px]
    else:
        # Upsample with linear interpolation
        # preserve_range=True to avoid rescaling to [0..1]
        resized = skimage_resize(
            image=image,
            output_shape=(height_px, width_px),
            order=1,  # 1 = linear interpolation
            preserve_range=True,
            anti_aliasing=False,
        )

    # 11. Convert to desired integer dtype (e.g., uint16)
    final_image = resized.astype(data_type)

    return final_image


def generate_reference_image_raw(
    height_px: int,
    width_px: int,
    data_type: np.dtype = np.dtype(np.uint16),
    reference_image_path: str = REFERENCE_IMAGE_PATH,
    resize_method=FrameGenStrategy.UPSAMPLE,
) -> np.ndarray:
    """
    Loads a TIFF, converts to the desired dtype, and resizes by either tiling or upsampling.
    No additional scaling or noise is applied.
    """
    # 1. Load TIFF into a NumPy array
    # image = tifffile.imread(reference_image_path)
    image = load_and_normalize_tiff(reference_image_path, data_type)

    # # 2. Cast to the desired data type
    # image = image.astype(data_type)

    # 4. Resize
    resized_jimage = resize_image_jit(image, height_px, width_px, resize_method)

    # 5. Convert back to NumPy
    return np.array(resized_jimage, dtype=data_type)


def generate_reference_image_batch(
    nframes: int,
    height_px: int,
    width_px: int,
    reference_image_path: str = REFERENCE_IMAGE_PATH,
    exposure_time_ms: int = EXPOSURE_TIME_MS,
    resize_method=FrameGenStrategy.UPSAMPLE,
) -> jnp.ndarray:
    # Load the image and convert it to jax.numpy array
    image = tifffile.imread(reference_image_path)
    rng_key = random.PRNGKey(42)  # Replace with a dynamically generated seed if needed
    return process_image_batch_jit(
        jnp.array(image),
        nframes=nframes,
        height_px=height_px,
        width_px=width_px,
        rng_key=rng_key,
        exposure_time_ms=exposure_time_ms,
        resize_method=resize_method,
    )


def downsample_image_by_decimation(image: np.ndarray, factor: int) -> np.ndarray:
    """
    Downsample an image by a given factor.

    This method of downsampling is called "decimation" or "subsampling".

    Parameters:
    image (np.ndarray): The input image to be downsampled.
    factor (int): The factor by which to downsample the image. For example, a factor of 2 will reduce the image dimensions by half.

    Returns:
    np.ndarray: The downsampled image.
    """
    return np.array(image[::factor, ::factor])


@jit
def compute_checkered_pattern(
    z_abs: jnp.ndarray, y: jnp.ndarray, x: jnp.ndarray, initial_size: int, final_size: int
) -> jnp.ndarray:
    """
    Create a 3D JAX array with a dynamically varying checker pattern.
    :param z_abs: Precomputed Z positions.
    :type z_abs: jnp.ndarray
    :param y: Precomputed Y indices.
    :type y: jnp.ndarray
    :param x: Precomputed X indices.
    :type x: jnp.ndarray
    :param initial_size: Precomputed initial checker size.
    :type initial_size: int
    :param final_size: Precomputed final checker size.
    :type final_size: int
    :return: A 3D array with the dynamic checker pattern.
    :rtype: jnp.ndarray
    """
    nframes = z_abs.shape[0]

    # Calculate checker sizes dynamically
    t = z_abs / (nframes - 1)
    checker_size = initial_size - (initial_size - final_size) * t
    checker_size = jnp.maximum(1, jnp.round(checker_size).astype(jnp.int32))

    # Generate the checkered pattern
    checker_pattern = ((x[None, :, :] // checker_size) + (y[None, :, :] // checker_size) + z_abs) % 2

    # Scale pattern to 16-bit integers
    images = checker_pattern * 65535
    return images.astype(jnp.uint16)


def generate_checkered_batch(
    nframes: int, height_px: int, width_px: int, chunk_size: int, z_idx: int = 0
) -> np.ndarray:
    """
    Wrapper function to precompute inputs for the JIT-compiled function.
    """
    # Precompute static indices
    y, x = jnp.indices((height_px, width_px))
    start_z = z_idx * nframes
    z_abs = start_z + jnp.arange(nframes)[:, None, None]  # Add Z dimension

    # Precompute initial and final sizes for the checker pattern
    initial_size = chunk_size
    final_size = min(width_px // 10, chunk_size * 10)

    # Call the JIT-compiled function
    return compute_checkered_pattern(z_abs, y, x, initial_size, final_size)


def generate_checkered_frame(height_px: int, width_px: int, data_type: np.dtype = np.dtype(np.uint16)) -> np.ndarray:
    """
    Generate a single checkered frame without jax
    """
    y, x = np.indices((height_px, width_px))
    checker_size = 10
    checker_pattern = ((x // checker_size) + (y // checker_size)) % 2

    # Scale pattern to 16-bit integers
    max_val = np.iinfo(data_type).max
    images = checker_pattern * max_val
    return images.astype(data_type)


def generate_spiral_frames(frame_count, frame_shape, dtype, logger: "LoggerType | None" = None):
    """Generate frames with spiral patterns."""
    min_tile_size = 2
    max_tile_size = min(frame_shape.x, frame_shape.y) // 12

    tile_sizes = np.linspace(min_tile_size, max_tile_size, num=frame_count, dtype=int, retstep=False)

    # Create indices centered on the frame (precomputed)
    y_indices = np.arange(frame_shape.y) - frame_shape.y // 2
    x_indices = np.arange(frame_shape.x) - frame_shape.x // 2
    xv, yv = np.meshgrid(x_indices, y_indices)

    # Precompute distance from the center
    distance = np.sqrt(xv**2 + yv**2)

    for frame_z in range(frame_count):
        start_time = time.time()
        tile_size = tile_sizes[frame_z]

        # Create expanding pattern
        pattern = ((distance // tile_size) % 2).astype(dtype)

        # Scale to full intensity range
        frame = pattern * 255

        end_time = time.time()
        time_taken = end_time - start_time
        if logger:
            logger.debug(f"Frame {frame_z} generated in {time_taken:.6f} seconds")

        yield frame


def generate_spiral_frame(width: int, height: int, data_type: np.dtype):
    """Generate a single spiral frame."""
    # Create indices centered on the frame
    y_indices = np.arange(height) - height // 2
    x_indices = np.arange(width) - width // 2
    xv, yv = np.meshgrid(x_indices, y_indices)

    max_val = np.iinfo(data_type).max

    # Precompute distance from the center
    distance = np.sqrt(xv**2 + yv**2)

    # Create expanding pattern
    pattern = (distance // 10) % 2

    # Scale to full intensity range
    frame = pattern * max_val

    return frame


def generate_ripple_frame(
    width: int,
    height: int,
    data_type: np.dtype,
    ring_count: int = 20,
    duty_cycle: float = 0.5,
):
    """
    Generate a single frame that resembles ripples with concentric rings.

    The image is composed of alternating rings where the crest (the black portion)
    is defined by the duty cycle parameter. A duty cycle of 1.0 results in fully
    black rings, while a duty cycle of 0 results in fully white rings.

    Parameters:
    - width, height: Dimensions of the output frame.
    - data_type: Numpy data type for the frame (e.g. np.uint8).
    - ring_count: Number of rings to generate (controls the spacing of the ripples).
    - duty_cycle: Normalized value (0 to 1) defining the fraction of each ring's period
                  that is the crest (black). For example, 0.3 means that 30% of each ring's
                  period is black (the crest) and the remaining 70% is white.

    Returns:
    - frame: A numpy array with the ripple pattern.
    """
    max_val = np.iinfo(data_type).max
    # Compute the maximum radius available (half the smallest dimension)
    max_radius = min(width, height) / 2.0
    # Automatically compute ring thickness so that ring_count rings fill the max_radius
    ring_thickness = max_radius / ring_count

    # Determine the width of the black crest within each ring period
    crest_width = ring_thickness * duty_cycle

    # Create coordinate indices centered on the frame
    y_indices = np.arange(height) - height // 2
    x_indices = np.arange(width) - width // 2
    xv, yv = np.meshgrid(x_indices, y_indices)

    # Compute the distance from the center for each pixel
    distance = np.sqrt(xv**2 + yv**2)

    # Determine the position within each ring period
    ring_mod = distance % ring_thickness

    # Set pixel to black (0) if within the crest region, otherwise white (255)
    frame = np.where(ring_mod < crest_width, 0, max_val).astype(data_type)

    return frame
