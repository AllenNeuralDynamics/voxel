"""Wire-format schemas — one file per topic namespace.

The bus (:mod:`vxl_web.wire`) is transport; this package is the contract.
Each submodule defines the events and commands for one namespace, mirroring
the topic prefix on the wire (``app.*`` → ``protocol/app.py``, etc.).

Only cross-cutting types (``app.*`` events and shared utilities like
:class:`Empty`) are re-exported at the package root. Domain-specific types
live behind their namespace import (``from vxl_web.protocol.device import
DevicePropsUpdate``) so adding a new namespace doesn't bloat the package
surface.
"""

from pydantic import BaseModel

from .app import AppStatus, AppStatusUpdate, ErrorEvent, LogMessage


class Empty(BaseModel):
    """Body model for commands that carry no payload (``preview.start`` etc.).

    Defined once and reused across namespaces — beats writing a per-command
    empty class for every payload-less command.
    """


__all__ = [
    "AppStatus",
    "AppStatusUpdate",
    "Empty",
    "ErrorEvent",
    "LogMessage",
]
