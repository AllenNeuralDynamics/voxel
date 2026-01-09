"""Web interface for SPIM Rig control."""

from spim_web.server import create_rig_app
from spim_web.service import RigService

__all__ = ["create_rig_app", "RigService"]
