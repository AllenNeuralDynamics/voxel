"""vxlib: Shared types and utilities."""

from .color import (
    COLORMAP_CATALOG,
    Color,
    Colormap,
    ColormapGroup,
    get_colormap_catalog,
    resolve_colormap,
)
from .log import (
    configure_logging,
    get_uvicorn_log_config,
)
from .poller import Poller
from .types import Dtype, SchemaModel
from .utils import display_name, fire_and_forget, format_relative_time, get_local_ip, thread_safe_singleton
from .vec import IVec2D, IVec3D, UIVec2D, UIVec3D, UVec2D, UVec3D, Vec2D, Vec3D

__all__ = [
    "COLORMAP_CATALOG",
    "Color",
    "Colormap",
    "ColormapGroup",
    "Dtype",
    "IVec2D",
    "IVec3D",
    "Poller",
    "SchemaModel",
    "UIVec2D",
    "UIVec3D",
    "UVec2D",
    "UVec3D",
    "Vec2D",
    "Vec3D",
    "configure_logging",
    "display_name",
    "fire_and_forget",
    "format_relative_time",
    "get_colormap_catalog",
    "get_local_ip",
    "get_uvicorn_log_config",
    "resolve_colormap",
    "thread_safe_singleton",
]
