"""Asset paths for the Voxel application."""

from pathlib import Path

from .fonts import DEFAULT_FAMILY, load_fonts

_ASSETS_DIR = Path(__file__).parent

VOXEL_LOGO = _ASSETS_DIR / "voxel-logo.png"

__all__ = [
    "DEFAULT_FAMILY",
    "VOXEL_LOGO",
    "load_fonts",
]
