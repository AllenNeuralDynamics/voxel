"""Font loading utilities for the Voxel Qt application.

Usage:
    from voxel_qt.ui.assets.fonts import load_fonts, IBM_PLEX, GEIST

    # Load fonts early in app startup (after QApplication is created)
    load_fonts(IBM_PLEX)  # or GEIST
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QFontDatabase

log = logging.getLogger(__name__)

_FONTS_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Font:
    """A font with its name and fallbacks."""

    name: str
    fallbacks: tuple[str, ...] = ()

    @property
    def css(self) -> str:
        """Get CSS font-family string with fallbacks."""
        generic = {"sans-serif", "serif", "monospace", "cursive", "fantasy"}
        all_fonts = (self.name, *self.fallbacks)
        return ", ".join(f if f in generic else f'"{f}"' for f in all_fonts)


@dataclass(frozen=True)
class FontFamily:
    """A pair of sans and mono fonts."""

    sans: Font
    mono: Font
    files: tuple[str, ...]  # Font files to load (relative to family folder)
    folder: str  # Folder name under fonts/


# Presets
IBM_PLEX = FontFamily(
    sans=Font("IBM Plex Sans Var"),
    mono=Font("IBM Plex Mono"),
    files=(
        "sans/IBM Plex Sans Var-Roman.ttf",
        "mono/IBMPlexMono-Regular.ttf",
        "mono/IBMPlexMono-Medium.ttf",
        "mono/IBMPlexMono-SemiBold.ttf",
    ),
    folder="ibm-plex",
)

GEIST = FontFamily(
    sans=Font("Geist"),
    mono=Font("Geist Mono"),
    files=(
        "Geist[wght].ttf",
        "GeistMono[wght].ttf",
    ),
    folder="geist",
)

# Default font family
DEFAULT_FAMILY = IBM_PLEX


def load_fonts(family: FontFamily = DEFAULT_FAMILY) -> bool:
    """Load bundled fonts into the application.

    Must be called after QApplication is created but before widgets are shown.

    Args:
        family: Which font family to load.

    Returns:
        True if all fonts loaded successfully, False if any failed.
    """
    font_dir = _FONTS_DIR / family.folder

    if not font_dir.exists():
        log.warning("Font directory does not exist: %s", font_dir)
        return False

    success = True
    loaded = []

    for font_file in family.files:
        font_path = font_dir / font_file
        if not font_path.exists():
            log.warning("Font file not found: %s", font_path)
            success = False
            continue

        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            log.warning("Failed to load font: %s", font_file)
            success = False
        else:
            families = QFontDatabase.applicationFontFamilies(font_id)
            loaded.extend(families)
            log.debug("Loaded font: %s -> %s", font_file, families)

    if loaded:
        log.info("Loaded fonts: %s", ", ".join(set(loaded)))

    return success
