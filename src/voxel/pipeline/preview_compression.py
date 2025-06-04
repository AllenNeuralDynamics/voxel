import zlib
from enum import StrEnum

import cv2
import numpy as np


def convert_to_jpeg(frame: np.ndarray, quality: int = 100) -> bytes:
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


class PreviewCompression(StrEnum):
    RAW = "raw"
    JPEG = "jpeg"
    PNG = "png"
    ZLIB = "zlib"

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


# class PreviewCorrection(BaseModel):
#     black: float = Field(default=0.0, ge=0.0, le=1.0, description="black point of the preview")
#     white: float = Field(default=1.0, ge=0.0, le=1.0, description="white point of the preview")
#     gamma: float = Field(default=1.0, ge=0.0, le=10.0, description="gamma correction of the preview")

#     # add validators to ensure that b < w


# class PreviewSettings(BaseModel):
#     """
#     Defines the preview configuration, including ROI (region of interest),
#     target preview size, and black/white points as fractions of the
#     sensor's full dynamic range. Also supports optional gamma correction.
#     """

#     # Preview resolution and ROI
#     transform: PreviewDisplayOptions = Field(default=PreviewDisplayOptions(), description="Preview transform.")
#     correction: PreviewCorrection = Field(default=PreviewCorrection(), description="Preview correction.")
#     compression: PreviewCompression = Field(default=PreviewCompression.JPEG, description="Preview compression.")


# class PreviewFrameDict(TypedDict):
#     config: dict[str, int | float]
#     data: bytes


# @dataclass
# class PreviewFrame:
#     metadata: PreviewMetadata
#     frame: np.ndarray

#     def dump(self) -> PreviewFrameDict:
#         return PreviewFrameDict(
#             config=self.metadata.model_dump(),
#             data=self.metadata.compression(frame=self.frame),
#         )

#     def pack(self) -> bytes:
#         return msgpack.packb({"config": self.metadata.model_dump(), "frame": self.frame}, default=mpack_numpy.encode)

#     @classmethod
#     def unpack(cls, packed_frame: bytes) -> Self:
#         unpacked = msgpack.unpackb(packed_frame, object_hook=mpack_numpy.decode)
#         return cls(frame=unpacked["frame"], metadata=PreviewMetadata(**unpacked["config"]))
