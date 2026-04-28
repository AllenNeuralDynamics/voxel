"""Wire schemas for the ``app.*`` topic namespace.

Cross-cutting events (status, log, error) consumed by every frontend client.
Re-exported from :mod:`vxl_web.protocol` for convenience.
"""

from typing import Literal

from pydantic import BaseModel

from .session import SessionStateUpdate

# ==================== Events ====================

AppStatus = Literal["idle", "launching", "ready"]


class AppStatusUpdate(BaseModel):
    """Broadcast on ``app.status`` whenever the app or session lifecycle changes."""

    status: AppStatus
    session: SessionStateUpdate | None = None
    timestamp: str


class LogMessage(BaseModel):
    """Broadcast on ``app.log.message`` for every captured log record."""

    level: str
    message: str
    logger: str
    timestamp: str


class ErrorEvent(BaseModel):
    """Broadcast on ``app.error`` when any service surfaces a recoverable error.

    ``topic`` carries the originating context (e.g. an inbound WS topic that
    the handler rejected, or a lifecycle stage like ``session/launch``).
    """

    error: str
    topic: str | None = None


# ==================== Commands ====================

# (none yet — request_status currently rides on the legacy ws path)
