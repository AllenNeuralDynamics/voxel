from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

import cv2
import msgpack
import msgpack_numpy as mpack_numpy
import numpy as np
from pydantic import BaseModel, Field

from .preview_compression import PreviewCompression


class PreviewOptions(BaseModel):
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
    options: PreviewOptions = Field(default=PreviewOptions(), description="Preview display options.")


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


class PreviewManager:
    def __init__(self, preview_width: int = 1024):
        self._preview_width = preview_width
        self._latest_frame: np.ndarray | None = None

        self._observers: list[NewFrameCallback] = []
        self._display_options = PreviewOptions()

    def set_new_frame(self, frame: np.ndarray, frame_idx: int, channel_name: str) -> None:
        self._latest_frame = frame
        # send full frame to observers
        preview_frame = self._generate_preview_frame(raw_frame=frame, frame_idx=frame_idx, channel_name=channel_name)
        self.notify_new_frame_observers(preview_frame)

        # if display options are set, generate an optimized preview and notify observers
        if self._display_options.needs_processing():
            preview_frame = self._generate_preview_frame(frame, frame_idx, channel_name, apply_transform=True)
            self.notify_new_frame_observers(preview_frame)

    def notify_new_frame_observers(self, frame: PreviewFrame) -> None:
        """Notify all registered observers about a new frame."""
        for observer in self._observers:
            observer(frame)

    def register_new_frame_observer(self, observer: NewFrameCallback) -> None:
        """Register a new observer for new frames."""
        if observer not in self._observers:
            self._observers.append(observer)

    def unregister_new_frame_observer(self, observer: NewFrameCallback) -> None:
        """Unregister an observer for new frames."""
        if observer in self._observers:
            self._observers.remove(observer)

    def update_display_options(self, options: PreviewOptions) -> None:
        """Update the preview display options."""
        self._display_options = options

    def _generate_preview_frame(
        self,
        raw_frame: np.ndarray,
        frame_idx: int,
        channel_name: str,
        apply_transform: bool = False,
    ) -> PreviewFrame:
        """
        Generate a PreviewFrame from the raw frame using the current preview_settings.
        The method crops the raw frame to the ROI (using normalized coordinates) and then
        resizes the cropped image to the target preview dimensions. It also applies black/white
        point and gamma adjustments to produce an 8-bit preview.
        """
        transform = self._display_options if apply_transform else PreviewOptions()

        full_width = raw_frame.shape[1]
        full_height = raw_frame.shape[0]
        preview_width = self._preview_width
        preview_height = int(full_height * (self._preview_width / full_width))

        # 1) Compute absolute ROI coordinates.
        if apply_transform:
            zoom = 1 - transform.k  # for k 0.0 is no zoom, 1.0 is full zoom
            roi_x0 = int(full_width * transform.x)
            roi_y0 = int(full_height * transform.y)
            roi_x1 = roi_x0 + int(full_width * zoom)
            roi_y1 = roi_y0 + int(full_height * zoom)

            # 2) Crop to the ROI.
            # 3) Resize to the target dimensions (still in the original dtype, e.g. uint16).
            raw_frame = raw_frame[roi_y0:roi_y1, roi_x0:roi_x1]

        preview_img = cv2.resize(raw_frame, (preview_width, preview_height), interpolation=cv2.INTER_AREA)

        # 4) Convert to float32 for intensity scaling.
        preview_float = preview_img.astype(np.float32)

        if apply_transform:
            # 5) Determine the max possible value from the raw frame's dtype (e.g. 65535 for uint16).
            # 6) Compute the actual black/white values from percentages.
            # 7) Clamp to [black_val..white_val].
            max_val = np.iinfo(raw_frame.dtype).max
            black_val = transform.black * max_val
            white_val = transform.white * max_val
            preview_float = np.clip(preview_float, black_val, white_val)

            # 8) Normalize to [0..1].
            denom = (white_val - black_val) + 1e-8
            preview_float = (preview_float - black_val) / denom

            # 9) Apply gamma correction (gamma factor in PreviewSettings).
            #    If gamma=1.0, no change.
            if (g := transform.gamma) != 1.0:
                preview_float = preview_float ** (1.0 / g)

        # 10) Scale to [0..255] and convert to uint8.
        preview_float *= 255.0
        preview_uint8 = preview_float.astype(np.uint8)

        # Build the metadata object (assuming PreviewMetadata supports these fields).
        metadata = PreviewMetadata(
            frame_idx=frame_idx,
            channel_name=channel_name,
            preview_width=preview_width,
            preview_height=preview_height,
            full_width=full_width,
            full_height=full_height,
            options=transform,
        )

        # 11) Return the final 8-bit preview.
        return PreviewFrame.from_array(frame_array=preview_uint8, metadata=metadata)
