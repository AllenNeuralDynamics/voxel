from collections.abc import Callable
from typing import TypedDict
import zlib

import cv2
import msgpack
import msgpack_numpy as mpack_numpy
import numpy as np
from pydantic import BaseModel, Field


class PreviewSettings(BaseModel):
    """
    Defines the preview configuration, including ROI (region of interest),
    target preview size, and black/white points as fractions of the
    sensor's full dynamic range. Also supports optional gamma correction.
    """

    # Preview resolution and ROI
    preview_width: int = Field(..., gt=0, description="Target preview width in pixels.")
    roi_width: float = Field(..., gt=0.0, le=1.0, description="Normalized width of the ROI.")
    roi_height: float = Field(..., gt=0.0, le=1.0, description="Normalized height of the ROI.")
    roi_x: float = Field(..., ge=0.0, le=1.0, description="Normalized X coordinate of ROI top-left corner.")
    roi_y: float = Field(..., ge=0.0, le=1.0, description="Normalized Y coordinate of ROI top-left corner.")

    # Black/white points as a fraction of the full sensor range [0..max_val].
    # E.g. for 16-bit data, max_val=65535 => black_val = black_percent * 65535
    black_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of the sensor's full range mapped to 0 in the preview. "
            "0.0 means minimum intensity, 1.0 means maximum intensity."
        ),
    )
    white_percent: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of the sensor's full range mapped to 255 in the preview. "
            "Typically >= black_percent. 1.0 means maximum intensity."
        ),
    )

    # Optional gamma correction
    gamma: float = Field(
        default=1.0, gt=0.0, description=("Gamma correction factor. " "A value of 1.0 means no gamma correction.")
    )


class PreviewMetadata(PreviewSettings):
    """
    Contains the preview configuration plus the full image dimensions,
    which are determined from the captured frame.
    """

    preview_height: int = Field(..., gt=0, description="Target preview height in pixels.")
    full_width: int = Field(..., gt=0, description="Full image width in pixels (from captured frame).")
    full_height: int = Field(..., gt=0, description="Full image height in pixels (from captured frame).")
    frame_idx: int = Field(..., ge=0, description="Frame index of the captured image.")
    compression: str = Field(
        default="jpeg",
        description="Compression format used for the preview frame. Options: 'raw', 'zlib','jpeg', 'png'.",
    )
    # bitdepth: int = Field(
    #     default=8,
    #     ge=1,
    #     le=16,
    #     description="Bit depth of the captured image. Typically 8 or 16 bits per channel.",
    # )


def convert_to_jpeg(frame: np.ndarray, quality: int = 80) -> bytes:
    """
    Convert a NumPy array (BGR image) to JPEG-encoded bytes using OpenCV.
    """
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, encoded_image = cv2.imencode(".jpg", frame, encode_params)
    if not success:
        raise RuntimeError("JPEG encoding failed")
    return encoded_image.tobytes()


def convert_to_png(frame: np.ndarray) -> bytes:
    """
    Convert a NumPy array (BGR image) to PNG-encoded bytes using OpenCV.
    """
    encode_params = [int(cv2.IMWRITE_PNG_COMPRESSION), 0]
    success, encoded_image = cv2.imencode(".png", frame, encode_params)
    if not success:
        raise RuntimeError("PNG encoding failed")
    return encoded_image.tobytes()


def convert_to_raw(frame: np.ndarray) -> bytes:
    """
    Return the raw bytes of the NumPy array without any compression or encoding.
    Useful if you want to preserve the full bit depth (e.g. uint16).
    """
    return frame.tobytes()


def compress_uint16_frame_zlib(frame: np.ndarray) -> bytes:
    """
    Compress a 2D (or 3D) NumPy array of dtype=uint16 with zlib.
    Returns the compressed bytes.
    """
    # Ensure the array is C-contiguous, just in case
    if not frame.flags["C_CONTIGUOUS"]:
        frame = np.ascontiguousarray(frame)

    # Convert to raw bytes
    raw_bytes = frame.tobytes()

    # Compress with zlib (level=9 = max compression, can adjust for speed)
    compressed = zlib.compress(raw_bytes, level=9)
    return compressed


compressor_map = {
    "raw": convert_to_raw,
    "jpeg": convert_to_jpeg,
    "png": convert_to_png,
    "zlib": compress_uint16_frame_zlib,
}


DEFAULT_PREVIEW_SETTINGS = PreviewSettings(
    preview_width=2048,
    roi_width=1.0,
    roi_height=1.0,
    roi_x=0.0,
    roi_y=0.0,
)


class PreviewFrameDict(TypedDict):
    metadata: dict[str, int | float]
    data: bytes


class PreviewFrame:
    def __init__(self, frame: np.ndarray, metadata: PreviewMetadata, compression: str = "jpeg") -> None:
        self.metadata = metadata
        self.data = compressor_map[compression](frame)
        self.metadata.compression = compression

    def dump(self) -> PreviewFrameDict:
        # print(f"Data size in MBs: {len(self.data) / (1024 * 1024):.2f} - Compression: {self.metadata.compression}")
        return PreviewFrameDict(
            metadata=self.metadata.model_dump(),
            data=self.data,
        )


type NewFrameCallback = Callable[[PreviewFrame], None]


def pack_preview_frame(preview: PreviewFrame) -> bytes:
    """
    Pack the preview frame along with its metadata using msgpack.
    The result is a bytes object that can be transmitted over RPC.
    """
    return msgpack.packb(
        {
            "data": preview.data,  # msgpack-numpy handles numpy arrays.
            "metadata": preview.metadata.model_dump(),
        },
        default=mpack_numpy.encode,
    )


def unpack_preview_frame(packed_frame: bytes) -> PreviewFrame:
    """
    Unpack the packed preview frame using msgpack.
    The result is a PreviewFrame object.
    """
    unpacked = msgpack.unpackb(packed_frame, object_hook=mpack_numpy.decode)
    data = unpacked["data"]
    metadata = PreviewMetadata(**unpacked["metadata"])
    return PreviewFrame(frame=data, metadata=metadata)
