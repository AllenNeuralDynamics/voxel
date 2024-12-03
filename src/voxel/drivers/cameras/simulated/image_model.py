from dataclasses import dataclass
import os
from typing import TypedDict

import numpy as np
import tifffile

from voxel.utils.vec import Vec2D


class ImageModelParams(TypedDict):
    qe: float
    gain: float
    dark_noise: float
    bitdepth: int
    baseline: int
    reference_image_path: str | None
    size: Vec2D[int]


def _default_reference_image_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "reference_image.tif")


DEFAULT_IMAGE_MODEL: ImageModelParams = {
    "qe": 0.85,
    "gain": 0.08,
    "dark_noise": 6.89,
    "bitdepth": 12,
    "baseline": 0,
    "reference_image_path": _default_reference_image_path(),
    "size": Vec2D(2048 + 2, 2048 + 2),
}


@dataclass
class ROI:
    origin: Vec2D
    size: Vec2D[int]
    bounds: Vec2D

    def __repr__(self):
        return f"\n" f"  Origin    = {self.origin}, \n" f"  Size      = {self.size}, \n" f"  Bounds    = {self.bounds}"


class ImageModel:
    def __init__(self, qe, gain, dark_noise, bitdepth, baseline, reference_image_path, size: Vec2D[int]) -> None:
        self.raw_reference_image = tifffile.imread(reference_image_path)
        self.sensor_size_px = size
        self.qe = qe
        self.gain = gain
        self.dark_noise = dark_noise
        self.bitdepth = bitdepth
        self.baseline = baseline

    def __repr__(self):
        return (
            f"ImageModel(qe={self.qe}, "
            f"gain={self.gain}, "
            f"dark_noise={self.dark_noise}, "
            f"bitdepth={self.bitdepth}, "
            f"baseline={self.baseline})"
        )

    @staticmethod
    def _upsample_image(image: np.ndarray, target_size: Vec2D[int]) -> np.ndarray:
        # Calculate how many times the image needs to be repeated to cover the target size
        tile_y = (target_size.y + image.shape[0] - 1) // image.shape[0]
        tile_x = (target_size.x + image.shape[1] - 1) // image.shape[1]

        # Tile the image to exceed the target size
        tiled_image = np.tile(image, (tile_y, tile_x))

        # Crop the tiled image to the target size
        return tiled_image[: target_size.y, : target_size.x]

    def generate_frame(self, exposure_time, roi: ROI, pixel_type):
        # Scale the reference image based on exposure time and ROI
        scaled_image = self.raw_reference_image * (exposure_time / 0.1)
        roi_image = self._apply_roi(scaled_image, roi)

        # Add noise to the image
        noisy_image = self._add_camera_noise(roi_image)

        full_image = self._upsample_image(noisy_image, self.sensor_size_px)

        # Convert to the correct pixel type
        return full_image.astype(pixel_type)

    @staticmethod
    def _apply_roi(image, roi: ROI):
        # crop the center of the image
        start_h = roi.origin.y
        start_w = roi.origin.x
        return image[start_h : start_h + roi.size.x, start_w : start_w + roi.size.y]

    def _add_camera_noise(self, image):
        # Add shot noise
        photons = np.random.poisson(image)

        # Convert to electrons
        electrons = self.qe * photons

        # Add dark noise
        electrons_out = np.random.normal(scale=self.dark_noise, size=electrons.shape) + electrons

        # Convert to ADU and add baseline
        max_adu = 2**self.bitdepth - 1
        image_out = (electrons_out * self.gain).astype(int)
        image_out += self.baseline
        np.clip(image_out, 0, max_adu, out=image_out)

        return image_out
