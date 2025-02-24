from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, Field


class PreviewSettings(BaseModel):
    """
    Defines the preview configuration.
    The target preview size is given in pixels and the ROI is defined in normalized coordinates.
    """

    target_width: int = Field(..., gt=0, description="Target preview width in pixels.")
    target_height: int = Field(..., gt=0, description="Target preview height in pixels.")
    roi_width: float = Field(..., gt=0.0, le=1.0, description="Normalized width of the ROI.")
    roi_height: float = Field(..., gt=0.0, le=1.0, description="Normalized height of the ROI.")
    roi_x: float = Field(..., ge=0.0, le=1.0, description="Normalized X coordinate of ROI top-left corner.")
    roi_y: float = Field(..., ge=0.0, le=1.0, description="Normalized Y coordinate of ROI top-left corner.")


class PreviewMetadata(PreviewSettings):
    """
    Contains the preview configuration plus the full image dimensions,
    which are determined from the captured frame.
    """

    full_width: int = Field(..., gt=0, description="Full image width in pixels (from captured frame).")
    full_height: int = Field(..., gt=0, description="Full image height in pixels (from captured frame).")


# Default preview settings (without full image dimensions)
DEFAULT_PREVIEW_SETTINGS = PreviewSettings(
    target_width=800,
    target_height=600,
    roi_width=1.0,
    roi_height=1.0,
    roi_x=0.0,
    roi_y=0.0,
)


@dataclass
class PreviewFrame:
    """
    Data structure that holds a preview image and its metadata.
    """

    data: np.ndarray
    metadata: PreviewMetadata


type NewFrameCallback = Callable[[PreviewFrame | bytes], None]
