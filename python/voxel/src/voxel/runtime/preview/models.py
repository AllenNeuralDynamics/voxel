from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

import msgpack
import msgpack_numpy as mpack_numpy
import numpy as np
from pydantic import BaseModel, Field

from .converters import PreviewCompression


class PreviewManagerOptions(BaseModel):
    listening_port: int = 4040
    target_width: int = 1024


class PreviewRelayOptions(BaseModel):
    manager_ip: str
    target_width: int
    publish_port: int


class PreviewConfigUpdates(BaseModel):
    """Partial or complete preview config."""

    x: float | None = Field(default=None, ge=0.0, le=1.0, description='normalized X coordinate of the preview.')
    y: float | None = Field(default=None, ge=0.0, le=1.0, description='normalized Y coordinate of the preview.')
    k: float | None = Field(default=None, ge=0.0, le=1.0, description='zoom factor - 0.0 no zoom, 1.0 full zoom.')
    black: float | None = Field(default=None, ge=0.0, le=1.0, description='black point of the preview')
    white: float | None = Field(default=None, ge=0.0, le=1.0, description='white point of the preview')
    gamma: float | None = Field(default=None, ge=0.0, le=10.0, description='gamma correction of the preview')


class PreviewConfig(BaseModel):
    x: float = Field(default=0.0, ge=0.0, le=1.0, description='normalized X coordinate of the preview.')
    y: float = Field(default=0.0, ge=0.0, le=1.0, description='normalized Y coordinate of the preview.')
    k: float = Field(default=0.0, ge=0.0, le=1.0, description='zoom factor - 0.0 no zoom, 1.0 full zoom.')
    black: float = Field(default=0.0, ge=0.0, le=1.0, description='black point of the preview')
    white: float = Field(default=1.0, ge=0.0, le=1.0, description='white point of the preview')
    gamma: float = Field(default=1.0, ge=0.0, le=10.0, description='gamma correction of the preview')

    def needs_processing(self) -> bool:
        """Check if any display options require processing.
        Either zoomed in (k != 0.0), or with adjusted black/white points or gamma.
        """
        return self.k != 0.0 or self.black != 0.0 or self.white != 1.0 or self.gamma != 1.0

    def update(self, options: 'PreviewConfigUpdates') -> None:
        """Update the preview configuration with new options.
        Only updates fields that are provided (not None).
        """
        for field_name, value in options.model_dump().items():
            if value is not None:
                setattr(self, field_name, value)


class PreviewMetadata(BaseModel):
    """Contains the preview configuration settings for a frame including the config used to generate it.
    """

    frame_idx: int = Field(..., ge=0, description='Frame index of the captured image.')
    channel_name: str = Field(..., description='Name of the channel from which the frame was captured.')
    preview_width: int = Field(default=2048 // 2, gt=0, description='Target preview width in pixels.')
    preview_height: int = Field(..., gt=0, description='Target preview height in pixels.')
    full_width: int = Field(..., gt=0, description='Full image width in pixels (from captured frame).')
    full_height: int = Field(..., gt=0, description='Full image height in pixels (from captured frame).')
    compression: PreviewCompression = Field(default=PreviewCompression.JPEG, description='Preview compression.')
    config: PreviewConfig = Field(default=PreviewConfig(), description='Preview display options.')


@dataclass(frozen=True)
class PreviewFrame:
    metadata: PreviewMetadata
    frame: bytes

    @classmethod
    def from_array(cls, frame_array: np.ndarray, metadata: PreviewMetadata) -> Self:
        """Create a PreviewFrame from a NumPy array and metadata.
        The frame is compressed using the specified compression method in metadata.
        """
        compressed_data = metadata.compression(frame_array)
        return cls(metadata=metadata, frame=compressed_data)

    @classmethod
    def from_packed(cls, packed_frame: bytes) -> Self:
        """Unpack a packed PreviewFrame from bytes.
        Returns a new PreviewFrame instance with the decompressed frame data.
        """
        unpacked = msgpack.unpackb(packed_frame, object_hook=mpack_numpy.decode)
        metadata = PreviewMetadata(**unpacked['metadata'])
        frame_data: bytes = unpacked['frame']

        return cls(metadata=metadata, frame=frame_data)

    def pack(self) -> bytes:
        """Pack the PreviewFrame into a bytes representation for transmission or storage.
        This includes both the metadata and the compressed frame data.
        """
        packed = msgpack.packb(
            {'metadata': self.metadata.model_dump(), 'frame': self.frame}, default=mpack_numpy.encode,
        )
        if packed is None:
            raise ValueError('Packing PreviewFrame failed: msgpack.packb returned None')
        return packed


type NewFrameCallback = Callable[[PreviewFrame], None]
