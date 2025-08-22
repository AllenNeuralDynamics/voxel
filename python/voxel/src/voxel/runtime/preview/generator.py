import cv2
import numpy as np

from .models import PreviewConfig, PreviewConfigUpdates, PreviewFrame, PreviewMetadata
from .publisher import PreviewFramePublisher


class PreviewGenerator:
    def __init__(self, publisher: PreviewFramePublisher):
        self._pub = publisher
        self._config = PreviewConfig()

    def update_config(self, options: PreviewConfigUpdates) -> None:
        """Update the preview display options."""
        self._config.update(options)

    def set_new_frame(self, frame: np.ndarray, frame_idx: int, channel_name: str) -> None:
        """Set a new frame for previewing. The generator will process it and call the hub to publish."""
        # send full frame to observers
        preview_frame = self._generate_preview_frame(raw_frame=frame, frame_idx=frame_idx, channel_name=channel_name)
        self._pub.publish_frame(preview_frame)

        # if display options are set, generate an optimized preview and notify observers
        if self._config.needs_processing():
            preview_frame = self._generate_preview_frame(frame, frame_idx, channel_name, apply_transform=True)
            self._pub.publish_frame(preview_frame)

    def _generate_preview_frame(
        self,
        raw_frame: np.ndarray,
        frame_idx: int,
        channel_name: str,
        apply_transform: bool = False,
    ) -> PreviewFrame:
        """Generate a PreviewFrame from the raw frame using the current preview_settings.
        The method crops the raw frame to the ROI (using normalized coordinates) and then
        resizes the cropped image to the target preview dimensions. It also applies black/white
        point and gamma adjustments to produce an 8-bit preview.
        """
        transform = self._config if apply_transform else PreviewConfig()

        full_width = raw_frame.shape[1]
        full_height = raw_frame.shape[0]
        preview_width = self._pub.target_width
        preview_height = int(full_height * (preview_width / full_width))

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
            config=transform,
        )

        # 11) Return the final 8-bit preview.
        return PreviewFrame.from_array(frame_array=preview_uint8, metadata=metadata)
