import zlib
from enum import StrEnum

import cv2
import numpy as np


class PreviewCompression(StrEnum):
    RAW = 'raw'
    JPEG = 'jpeg'
    PNG = 'png'
    ZLIB = 'zlib'

    def __call__(self, frame: np.ndarray) -> bytes:
        match self:
            case PreviewCompression.RAW:
                return convert_to_raw(frame)
            case PreviewCompression.JPEG:
                return convert_to_jpeg(frame)
            case PreviewCompression.PNG:
                return convert_to_png(frame)
            case PreviewCompression.ZLIB:
                return compress_uint16_frame_zlib(frame)


def convert_to_jpeg(frame: np.ndarray, quality: int = 100) -> bytes:
    """Convert a NumPy array (BGR image) to JPEG-encoded bytes using OpenCV."""
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, encoded_image = cv2.imencode('.jpg', frame, encode_params)
    if not success:
        raise RuntimeError('JPEG encoding failed')
    return encoded_image.tobytes()


def convert_to_png(frame: np.ndarray) -> bytes:
    """Convert a NumPy array (BGR image) to PNG-encoded bytes using OpenCV."""
    encode_params = [int(cv2.IMWRITE_PNG_COMPRESSION), 0]
    success, encoded_image = cv2.imencode('.png', frame, encode_params)
    if not success:
        raise RuntimeError('PNG encoding failed')
    return encoded_image.tobytes()


def convert_to_raw(frame: np.ndarray) -> bytes:
    """Return the raw bytes of the NumPy array without any compression or encoding.
    Useful if you want to preserve the full bit depth (e.g. uint16).
    """
    return frame.tobytes()


def compress_uint16_frame_zlib(frame: np.ndarray) -> bytes:
    """Compress a 2D (or 3D) NumPy array of dtype=uint16 with zlib.
    Returns the compressed bytes.
    """
    # Ensure the array is C-contiguous, just in case
    if not frame.flags['C_CONTIGUOUS']:
        frame = np.ascontiguousarray(frame)

    # Convert to raw bytes
    raw_bytes = frame.tobytes()

    # Compress with zlib (level=9 = max compression, can adjust for speed)
    return zlib.compress(raw_bytes, level=9)
