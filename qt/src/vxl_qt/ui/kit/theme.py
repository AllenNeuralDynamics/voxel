"""Design tokens for the Voxel Qt application.

This module provides a consistent design system used throughout the UI.
All colors follow a dark theme inspired by VS Code's dark+ theme.

Usage:
    from vxl_qt.ui.kit import Colors, Spacing, Color

    widget.setStyleSheet(f"background-color: {Colors.BG_DARK};")
    layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)

    # Color utilities
    c = Color("#3a6ea5")
    c.lighten(0.2)  # Lighter shade
"""

from __future__ import annotations

import base64
from enum import Enum, StrEnum
from functools import lru_cache

import qtawesome as qta
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor
from vxlib.color import Color

from vxl_qt.ui.assets import DEFAULT_FAMILY


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


class Colors:
    """Application color palette.

    Naming convention:
    - BG_* : Background colors (dark to light)
    - BORDER_* : Border colors
    - TEXT_* : Text colors
    - ACCENT_* : Accent/highlight colors
    - STATUS_* : Status indicator colors
    """

    # Backgrounds (dark to light)
    BG_DARK = Color("#010409")  # Main background
    BG_MEDIUM = Color("#0d1117")  # Cards, panels
    BG_LIGHT = Color("#161b22")  # Elevated surfaces, hover states

    # Borders
    BORDER = Color("#3d444d")  # Default border
    BORDER_LIGHT = Color("#4a5159")  # Subtle borders
    BORDER_FOCUS = Color("#575e66")  # Focused input borders
    BORDER_HOVER = Color("#656c75")  # Hover state borders

    # Text
    TEXT = Color("#f0f6fc")  # Primary text (titles)
    TEXT_BRIGHT = Color("#ffffff")  # Emphasized text
    TEXT_MUTED = Color("#9198a1")  # Secondary/hint text (field labels)
    TEXT_DISABLED = Color("#6e6e6e")  # Disabled text

    # Accent (primary action color)
    ACCENT = Color("#3a6ea5")  # Primary accent (blue)
    ACCENT_HOVER = Color("#4a7eb5")  # Accent hover state
    ACCENT_BRIGHT = Color("#0078d4")  # Bright accent for active states

    # Status colors
    SUCCESS = Color("#4ec9b0")  # Success/valid (teal)
    SUCCESS_HOVER = Color("#5ed4be")  # Success hover state
    SUCCESS_PRESSED = Color("#3db89a")  # Success pressed state
    WARNING = Color("#ffb74d")  # Warning (orange)
    ERROR = Color("#f44336")  # Error/danger (red)
    ERROR_HOVER = Color("#ff1744")  # Error hover state (same as ERROR_BRIGHT)
    ERROR_PRESSED = Color("#c62828")  # Error pressed state
    ERROR_BRIGHT = Color("#ff1744")  # Critical error

    # Interactive states
    HOVER = Color("#21262d")  # Generic hover background
    PRESSED = Color("#161b22")  # Pressed state
    SELECTED = Color("#0078d4")  # Selected item background

    # Toggle-specific colors
    TOGGLE_OFF_BG = Color("#2b323a")  # Toggle off background
    TOGGLE_OFF_THUMB = Color("#888f96")  # Toggle off thumb
    TOGGLE_OFF_BORDER = Color("#3d444d")  # Toggle off border


class Spacing:
    """Spacing scale for consistent layout.

    Use these values for margins, padding, and gaps.
    """

    XS = 2  # Extra small (tight spacing)
    SM = 4  # Small
    MD = 8  # Medium (default)
    LG = 12  # Large
    XL = 16  # Extra large
    XXL = 24  # Section spacing


class FontSize:
    """Font size scale."""

    XS = 10  # Caption text
    SM = 11  # Small text
    MD = 12  # Body text (default)
    LG = 14  # Headers
    XL = 16  # Section titles
    XXL = 20  # Page titles


class FontWeight(StrEnum):
    """Font weight options."""

    NORMAL = "normal"
    BOLD = "bold"


class BorderRadius:
    """Border radius values - soft-minimal design with subtle rounding."""

    SM = 2  # Default for most elements
    MD = 4  # Slightly rounded
    LG = 8  # Cards, dialogs
    XL = 12  # Pill-like chips, badges
    PILL = 16  # Fully rounded pills


class Size:
    """Standard sizes for UI element heights (icons, inputs, buttons).

    Usage:
        - Icons: XS (14), SM (16), MD (20)
        - Compact inputs/selects: MD (20)
        - Default inputs/buttons: LG (28)
        - Prominent buttons: XL (36)
    """

    XS = 14  # Small icons
    SM = 16  # Default icons
    MD = 20  # Compact inputs, small buttons
    LG = 28  # Default inputs, buttons
    XL = 36  # Large buttons, prominent controls
    XXL = 44  # Extra large / hero elements


class ControlSize(Enum):
    """Size presets for input components (TextInput, Select, SpinBox, etc.).

    Usage:
        TextInput(placeholder="name", size=ControlSize.MD)
        Select(options=["a", "b"], size=ControlSize.LG)

        # Access metrics
        ControlSize.SM.h     # 20 (height)
        ControlSize.SM.font  # 11 (font size)
        ControlSize.SM.px    # 4 (horizontal padding)
    """

    XS = "xs"
    SM = "sm"
    MD = "md"
    LG = "lg"
    XL = "xl"

    @property
    def h(self) -> int:
        """Height in pixels."""
        return {"XS": 12, "SM": 16, "MD": 20, "LG": 28, "XL": 36}[self.name]

    @property
    def font(self) -> int:
        """Font size in pixels."""
        return {"XS": FontSize.XS, "SM": FontSize.XS, "MD": FontSize.SM, "LG": FontSize.SM, "XL": FontSize.MD}[
            self.name
        ]

    @property
    def px(self) -> int:
        """Horizontal padding in pixels."""
        return {"XS": 2, "SM": 3, "MD": 4, "LG": 8, "XL": 10}[self.name]

    @property
    def radius(self) -> int:
        """Border radius in pixels."""
        return {"XS": 2, "SM": 2, "MD": 3, "LG": 4, "XL": 5}[self.name]


def app_stylesheet(sans_family: str = DEFAULT_FAMILY.sans.css) -> str:
    """Generate the application stylesheet with the specified font family."""
    return f"""
/* Base font */
QWidget {{
    font-family: {sans_family};
    font-size: {FontSize.MD}px;
}}

/* Tooltips */
QToolTip {{
    background-color: {Colors.BG_MEDIUM};
    color: {Colors.TEXT_BRIGHT};
    border: none;
    border-radius: {BorderRadius.SM}px;
    padding: {Spacing.XS}px {Spacing.SM}px;
}}

/* Scrollbars - vertical */
QScrollBar:vertical {{
    background: {Colors.BG_DARK};
    width: 6px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {Colors.BORDER};
    border-radius: {BorderRadius.SM}px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {Colors.BORDER_HOVER};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
    border: none;
}}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
}}

/* Scrollbars - horizontal */
QScrollBar:horizontal {{
    background: {Colors.BG_DARK};
    height: 6px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {Colors.BORDER};
    border-radius: {BorderRadius.SM}px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {Colors.BORDER_HOVER};
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
    border: none;
}}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* Scroll areas */
QScrollArea {{
    background: transparent;
    border: none;
}}

/* Menus */
QMenu {{
    background-color: {Colors.BG_MEDIUM};
    border: 1px solid {Colors.BORDER};
    border-radius: {BorderRadius.MD}px;
    padding: {Spacing.XS}px;
}}
QMenu::item {{
    padding: {Spacing.SM}px {Spacing.MD}px;
    border-radius: {BorderRadius.SM}px;
}}
QMenu::item:selected {{
    background-color: {Colors.HOVER};
}}
QMenu::separator {{
    height: 1px;
    background: {Colors.BORDER};
    margin: {Spacing.XS}px 0;
}}
"""


# Default stylesheet using IBM Plex
APP_STYLESHEET = app_stylesheet('"IBM Plex Sans Var"')
