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
from .signal import Cell, Signal, Sink, Unsub
from .types import Dtype, SchemaModel
from .utils import (
    bounded,
    display_name,
    fire_and_forget,
    format_relative_time,
    get_local_ip,
    merge_dicts,
    slugify,
    thread_safe_singleton,
)
from .vec import IVec2D, IVec3D, UIVec2D, UIVec3D, UVec2D, UVec3D, Vec2D, Vec3D

__all__ = [
    "COLORMAP_CATALOG",
    "Cell",
    "Color",
    "Colormap",
    "ColormapGroup",
    "Dtype",
    "IVec2D",
    "IVec3D",
    "Poller",
    "SchemaModel",
    "Signal",
    "Sink",
    "UIVec2D",
    "UIVec3D",
    "UVec2D",
    "UVec3D",
    "Unsub",
    "Vec2D",
    "Vec3D",
    "bounded",
    "configure_logging",
    "display_name",
    "fire_and_forget",
    "format_relative_time",
    "get_colormap_catalog",
    "get_local_ip",
    "get_uvicorn_log_config",
    "merge_dicts",
    "resolve_colormap",
    "slugify",
    "thread_safe_singleton",
]
