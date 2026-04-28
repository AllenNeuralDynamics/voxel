"""Wire schemas for the ``preview.*`` topic namespace.

Frame and tile binaries (``preview.frame.{channel}``, ``preview.tile.{channel}``)
are NOT typed events — they're a high-throughput binary stream owned by the
preview domain on the frontend. Same envelope, body is the raw msgpack frame
payload not a Pydantic dump.
"""

from pydantic import BaseModel

from vxl.camera.preview import PreviewLevels

# ==================== Body shapes (used for both inbound and outbound) ====================
#
# ``preview.viewport.set`` and ``preview.viewport.changed`` both carry a bare
# :class:`PreviewViewport`. The per-channel topics bundle channel + payload.


class PreviewLevelsUpdate(BaseModel):
    """Levels for one channel — body for ``preview.levels.{set,changed}``."""

    channel: str
    levels: PreviewLevels


class PreviewColormapUpdate(BaseModel):
    """Colormap for one channel — body for ``preview.colormap.{set,changed}``."""

    channel: str
    colormap: str
