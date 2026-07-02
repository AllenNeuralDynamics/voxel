"""vxlib: Shared types and utilities."""

from .coalescer import Coalescer
from .color import (
    COLORMAP_CATALOG,
    Color,
    Colormap,
    ColormapGroup,
    get_colormap_catalog,
    resolve_colormap,
)
from .document import JsonDocument
from .log import (
    configure_logging,
    get_uvicorn_log_config,
)
from .poller import Poller
from .reactivity import Cell, Computed, Derived, Emitter, ReactiveQuery, Readable, ReadableView, Subscribable
from .types import UNSET, AsyncTeardown, Dtype, SchemaModel, Teardown, UnsetType
from .utils import (
    atomic_write,
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
    "UNSET",
    "AsyncTeardown",
    "Cell",
    "Coalescer",
    "Color",
    "Colormap",
    "ColormapGroup",
    "Computed",
    "Derived",
    "Dtype",
    "Emitter",
    "IVec2D",
    "IVec3D",
    "JsonDocument",
    "Poller",
    "ReactiveQuery",
    "Readable",
    "ReadableView",
    "SchemaModel",
    "Subscribable",
    "Teardown",
    "UIVec2D",
    "UIVec3D",
    "UVec2D",
    "UVec3D",
    "UnsetType",
    "Vec2D",
    "Vec3D",
    "atomic_write",
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
