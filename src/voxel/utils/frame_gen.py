import logging
import os
import time
from typing import Literal

import numpy as np
import tifffile

os.environ["JAX_PLATFORM_NAME"] = "cpu"
os.environ["XLA_PYTHON_CLIENT_PREALLOCATE"] = "false"
import jax.numpy as jnp
from jax import config, jit, random
from jax.image import resize

jax_loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict if name.startswith("jax")]
for logger in jax_loggers:
    logger.setLevel(logging.WARNING)

config.update("jax_platform_name", "cpu")

REFERENCE_IMAGE_PATH = os.path.dirname(os.path.abspath(__file__)) + "/reference_image.tif"

EXPOSURE_TIME_MS = 10


def process_image_batch(
    image: jnp.ndarray,
    nframes: int,
    height_px: int,
    width_px: int,
    exposure_time_ms: int,
    resize_method: Literal["upsample", "tile"],
    rng_key: jnp.ndarray,
    qe: float = 0.85,
    gain: float = 0.08,
    dark_noise: float = 6.89,
    baseline: float = 0.0,
    bitdepth: int = 12,
) -> jnp.ndarray:
    """
    Add noise, resize the image, and create a batch of frames.
    """

    # Scale the image by exposure time
    image = image * exposure_time_ms / 0.1

    # Add shot noise (Poisson noise)
    photons = random.poisson(rng_key, image)

    # Convert to electrons with quantum efficiency
    electrons = qe * photons

    # Add dark noise (Gaussian noise)
    electrons += random.normal(rng_key, shape=electrons.shape) * dark_noise

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


def generate_reference_image_batch(
    nframes: int,
    height_px: int,
    width_px: int,
    reference_image_path: str = REFERENCE_IMAGE_PATH,
    exposure_time_ms: int = EXPOSURE_TIME_MS,
    resize_method: Literal["upsample", "tile"] = "upsample",
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


def generate_reference_image(
    height_px: int,
    width_px: int,
    reference_image_path: str = REFERENCE_IMAGE_PATH,
    exposure_time_ms: int = EXPOSURE_TIME_MS,
    resize_method: Literal["upsample", "tile"] = "upsample",
) -> np.ndarray:
    # Load the image and convert it to jax.numpy array
    image = tifffile.imread(reference_image_path)
    rng_key = random.PRNGKey(42)  # Replace with a dynamically generated seed if needed
    return process_image_batch_jit(
        jnp.array(image),
        nframes=1,
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


def generate_spiral_frames(frame_count, frame_shape, dtype, logger: logging.Logger | None = None):
    """Generate frames with spiral patterns."""
    min_tile_size = 2
    max_tile_size = min(frame_shape.x, frame_shape.y) // 12

    tile_sizes = np.linspace(min_tile_size, max_tile_size, num=frame_count, dtype=int)

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
