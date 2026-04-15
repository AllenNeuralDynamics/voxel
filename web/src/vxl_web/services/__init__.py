"""New web services layout — per-controller services mirroring backend peers.

Transitional package; replaces ``vxl_web.services`` once callers migrate.
"""

from .acquisition import AcquisitionService
from .app import AppService
from .app import router as app_router
from .devices import DevicesService
from .preview import PreviewService
from .profiles import ProfilesService
from .session import SessionService
from .stacks import StacksService
from .ws import BroadcastCallback, MsgQueue, WsHandler, WsRouter

__all__ = [
    "AcquisitionService",
    "AppService",
    "BroadcastCallback",
    "DevicesService",
    "MsgQueue",
    "PreviewService",
    "ProfilesService",
    "SessionService",
    "StacksService",
    "WsHandler",
    "WsRouter",
    "app_router",
]
