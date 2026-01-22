"""Shared utilities for UI primitives."""

import base64
from functools import lru_cache

import qtawesome as qta
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor


@lru_cache(maxsize=32)
def icon_data_uri(icon_name: str, color: str, size: int = 12) -> str:
    """Generate a data URI for a qtawesome icon.

    Args:
        icon_name: The qtawesome icon name (e.g., "mdi.chevron-down")
        color: The icon color as a hex string (e.g., "#888888")
        size: The icon size in pixels

    Returns:
        A CSS url() value containing the base64-encoded PNG icon
    """
    icon = qta.icon(icon_name, color=QColor(color))
    pixmap = icon.pixmap(size, size)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    b64 = base64.b64encode(buffer.data().data()).decode()
    return f"url(data:image/png;base64,{b64})"
