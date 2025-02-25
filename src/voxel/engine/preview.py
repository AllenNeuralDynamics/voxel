from collections.abc import Callable
from typing import TypedDict

import cv2
import msgpack
import msgpack_numpy as mpack_numpy
import numpy as np
from pydantic import BaseModel, Field


class PreviewSettings(BaseModel):
    """
    Defines the preview configuration.
    The target preview size is given in pixels and the ROI is defined in normalized coordinates.
    """

    preview_width: int = Field(..., gt=0, description="Target preview width in pixels.")
    roi_width: float = Field(..., gt=0.0, le=1.0, description="Normalized width of the ROI.")
    roi_height: float = Field(..., gt=0.0, le=1.0, description="Normalized height of the ROI.")
    roi_x: float = Field(..., ge=0.0, le=1.0, description="Normalized X coordinate of ROI top-left corner.")
    roi_y: float = Field(..., ge=0.0, le=1.0, description="Normalized Y coordinate of ROI top-left corner.")


class PreviewMetadata(PreviewSettings):
    """
    Contains the preview configuration plus the full image dimensions,
    which are determined from the captured frame.
    """

    preview_height: int = Field(..., gt=0, description="Target preview height in pixels.")
    full_width: int = Field(..., gt=0, description="Full image width in pixels (from captured frame).")
    full_height: int = Field(..., gt=0, description="Full image height in pixels (from captured frame).")
    frame_idx: int = Field(..., ge=0, description="Frame index of the captured image.")


# Default preview settings (without full image dimensions)
DEFAULT_PREVIEW_SETTINGS = PreviewSettings(
    preview_width=4096,
    roi_width=1.0,
    roi_height=1.0,
    roi_x=0.0,
    roi_y=0.0,
)
DEFAULT_PREVIEW_SETTINGS = PreviewSettings(
    preview_width=4096,
    roi_width=0.8,
    roi_height=0.8,
    roi_x=0.1,
    roi_y=0.1,
)


def convert_to_jpeg(frame: np.ndarray, quality: int = 80) -> bytes:
    """
    Convert a NumPy array (BGR image) to JPEG-encoded bytes using OpenCV.
    """
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, encoded_image = cv2.imencode(".jpg", frame, encode_params)
    if not success:
        raise RuntimeError("JPEG encoding failed")
    return encoded_image.tobytes()


class PreviewFrameDict(TypedDict):
    metadata: dict[str, int | float]
    data: bytes


class PreviewFrame:
    def __init__(self, data: np.ndarray, metadata: PreviewMetadata, quality: int = 80) -> None:
        self.metadata = metadata
        self.data = convert_to_jpeg(data, quality)

    def dump(self) -> PreviewFrameDict:
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
    return PreviewFrame(data=data, metadata=metadata)
