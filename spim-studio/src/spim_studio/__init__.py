"""Web interface for SPIM Rig control."""

from spim_studio.server import create_rig_app
from spim_studio.service import RigService

__all__ = ["create_rig_app", "RigService"]
