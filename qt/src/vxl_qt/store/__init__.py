"""State stores for Voxel application.

Stores provide centralized state management with Qt signals for reactive updates.

Stores:
    DevicesStore: Device adapters and property cache
    PreviewStore: Preview frames, crop state
    GridStore: Grid/tile/stack state for acquisition planning
    StageStore: Stage axis position, limits, moving state

Compositing functions:
    composite_rgb: Additively blend RGB frames
    crop_image: Crop image using normalized coordinates
    compute_local_crop: Compute local crop from frame/target crop difference
    blur_image: Apply Gaussian blur
"""

from vxl_qt.store.devices import DevicesStore
from vxl_qt.store.grid import (
    STACK_STATUS_COLORS,
    GridStore,
    LayerVisibility,
    get_stack_status_color,
)
from vxl_qt.store.preview import (
    ChannelData,
    PreviewStore,
    blur_image,
    composite_rgb,
    compute_local_crop,
    crop_image,
    resize_image,
)
from vxl_qt.store.stage import AxisState, StageStore

__all__ = [
    "STACK_STATUS_COLORS",
    "AxisState",
    "ChannelData",
    "DevicesStore",
    "GridStore",
    "LayerVisibility",
    "PreviewStore",
    "StageStore",
    "blur_image",
    "composite_rgb",
    "compute_local_crop",
    "crop_image",
    "get_stack_status_color",
    "resize_image",
]
