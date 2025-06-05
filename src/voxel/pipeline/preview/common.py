from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

import msgpack
import msgpack_numpy as mpack_numpy
import numpy as np
from pydantic import BaseModel, Field

from ._utils import (
    compress_uint16_frame_zlib,
    convert_to_jpeg,
    convert_to_png,
    convert_to_raw,
)


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


class PreviewConfigOptions(BaseModel):
    """Partial or complete preview config"""

    x: float | None = Field(default=None, ge=0.0, le=1.0, description="normalized X coordinate of the preview.")
    y: float | None = Field(default=None, ge=0.0, le=1.0, description="normalized Y coordinate of the preview.")
    k: float | None = Field(default=None, ge=0.0, le=1.0, description="zoom factor - 0.0 no zoom, 1.0 full zoom.")
    black: float | None = Field(default=None, ge=0.0, le=1.0, description="black point of the preview")
    white: float | None = Field(default=None, ge=0.0, le=1.0, description="white point of the preview")
    gamma: float | None = Field(default=None, ge=0.0, le=10.0, description="gamma correction of the preview")


class PreviewConfig(BaseModel):
    x: float = Field(default=0.0, ge=0.0, le=1.0, description="normalized X coordinate of the preview.")
    y: float = Field(default=0.0, ge=0.0, le=1.0, description="normalized Y coordinate of the preview.")
    k: float = Field(default=0.0, ge=0.0, le=1.0, description="zoom factor - 0.0 no zoom, 1.0 full zoom.")
    black: float = Field(default=0.0, ge=0.0, le=1.0, description="black point of the preview")
    white: float = Field(default=1.0, ge=0.0, le=1.0, description="white point of the preview")
    gamma: float = Field(default=1.0, ge=0.0, le=10.0, description="gamma correction of the preview")

    def needs_processing(self) -> bool:
        """
        Check if any display options require processing.
        Either zoomed in (k != 0.0), or with adjusted black/white points or gamma.
        """
        return self.k != 0.0 or self.black != 0.0 or self.white != 1.0 or self.gamma != 1.0

    def update(self, options: PreviewConfigOptions) -> None:
        """
        Update the preview configuration with new options.
        Only updates fields that are provided (not None).
        """
        for field_name, value in options.model_dump().items():
            if value is not None:
                setattr(self, field_name, value)


class PreviewMetadata(BaseModel):
    """
    Contains the preview configuration settings for a frame which combines the preview settings and other metadata.
    """

    frame_idx: int = Field(..., ge=0, description="Frame index of the captured image.")
    channel_name: str = Field(..., description="Name of the channel from which the frame was captured.")
    preview_width: int = Field(default=2048 // 2, gt=0, description="Target preview width in pixels.")
    preview_height: int = Field(..., gt=0, description="Target preview height in pixels.")
    full_width: int = Field(..., gt=0, description="Full image width in pixels (from captured frame).")
    full_height: int = Field(..., gt=0, description="Full image height in pixels (from captured frame).")
    compression: PreviewCompression = Field(default=PreviewCompression.JPEG, description="Preview compression.")
    config: PreviewConfig = Field(default=PreviewConfig(), description="Preview display options.")


@dataclass(frozen=True)
class PreviewFrame:
    metadata: PreviewMetadata
    frame: bytes

    @classmethod
    def from_array(cls, frame_array: np.ndarray, metadata: PreviewMetadata) -> Self:
        """
        Create a PreviewFrame from a NumPy array and metadata.
        The frame is compressed using the specified compression method in metadata.
        """
        compressed_data = metadata.compression(frame_array)
        return cls(metadata=metadata, frame=compressed_data)

    @classmethod
    def from_packed(cls, packed_frame: bytes) -> Self:
        """
        Unpack a packed PreviewFrame from bytes.
        Returns a new PreviewFrame instance with the decompressed frame data.
        """
        unpacked = msgpack.unpackb(packed_frame, object_hook=mpack_numpy.decode)
        metadata = PreviewMetadata(**unpacked["metadata"])
        frame_data: bytes = unpacked["frame"]

        return cls(metadata=metadata, frame=frame_data)

    def pack(self) -> bytes:
        """
        Pack the PreviewFrame into a bytes representation for transmission or storage.
        This includes both the metadata and the compressed frame data.
        """
        return msgpack.packb({"metadata": self.metadata.model_dump(), "frame": self.frame}, default=mpack_numpy.encode)


type NewFrameCallback = Callable[[PreviewFrame], None]


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
