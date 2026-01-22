"""Design tokens for the SPIM Qt application.

This module provides a consistent design system used throughout the UI.
All colors follow a dark theme inspired by VS Code's dark+ theme.

Usage:
    from spim_qt.theme import Colors, Spacing

    widget.setStyleSheet(f"background-color: {Colors.BG_DARK};")
    layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
"""


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
    BG_DARK = "#1e1e1e"  # Main background
    BG_MEDIUM = "#252526"  # Cards, panels
    BG_LIGHT = "#2d2d30"  # Elevated surfaces, hover states

    # Borders
    BORDER = "#3c3c3c"  # Default border
    BORDER_LIGHT = "#4a4a4a"  # Subtle borders
    BORDER_FOCUS = "#505050"  # Focused input borders
    BORDER_HOVER = "#606060"  # Hover state borders

    # Text
    TEXT = "#d4d4d4"  # Primary text
    TEXT_BRIGHT = "#ffffff"  # Emphasized text
    TEXT_MUTED = "#888888"  # Secondary/hint text
    TEXT_DISABLED = "#6e6e6e"  # Disabled text

    # Accent (primary action color)
    ACCENT = "#3a6ea5"  # Primary accent (blue)
    ACCENT_HOVER = "#4a7eb5"  # Accent hover state
    ACCENT_BRIGHT = "#0078d4"  # Bright accent for active states

    # Status colors
    SUCCESS = "#4ec9b0"  # Success/valid (teal)
    SUCCESS_HOVER = "#5ed4be"  # Success hover state
    SUCCESS_PRESSED = "#3db89a"  # Success pressed state
    WARNING = "#ffb74d"  # Warning (orange)
    ERROR = "#f44336"  # Error/danger (red)
    ERROR_HOVER = "#ff1744"  # Error hover state (same as ERROR_BRIGHT)
    ERROR_PRESSED = "#c62828"  # Error pressed state
    ERROR_BRIGHT = "#ff1744"  # Critical error

    # Interactive states
    HOVER = "#4a4a4d"  # Generic hover background
    PRESSED = "#2d2d30"  # Pressed state
    SELECTED = "#0078d4"  # Selected item background


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


class BorderRadius:
    """Border radius values - soft-minimal design with subtle rounding."""

    SM = 2  # Default for most elements
    MD = 4  # Slightly rounded
    LG = 8  # Cards, dialogs
    XL = 12  # Pill-like chips, badges
    PILL = 16  # Fully rounded pills


class Size:
    """Standard sizes for UI elements."""

    INPUT_HEIGHT = 26  # Consistent height for buttons, inputs, selects
    ICON_SM = 12  # Small icons
    ICON_MD = 14  # Default icon size
    ICON_LG = 16  # Large icons


# =============================================================================
# Color Utilities
# =============================================================================


def wavelength_to_rgb(wavelength_nm: float) -> tuple[float, float, float]:
    """Convert wavelength (nm) to RGB tuple with values in [0, 1].

    Uses gamma correction for better violet rendering on sRGB displays.
    Returns (0, 0, 0) if wavelength is outside visible range (~380-780 nm).
    """
    w = wavelength_nm

    if w < 380 or w > 780:
        return (0.0, 0.0, 0.0)

    # Calculate raw RGB based on wavelength
    if 380 <= w < 440:
        # Violet to Blue (reduced red to avoid magenta)
        r = 0.6 * (1.0 - (w - 380) / (440 - 380))
        g = 0.0
        b = 1.0
    elif 440 <= w < 490:
        # Blue to Cyan
        r = 0.0
        g = (w - 440) / (490 - 440)
        b = 1.0
    elif 490 <= w < 510:
        # Cyan to Green
        r = 0.0
        g = 1.0
        b = -(w - 510) / (510 - 490)
    elif 510 <= w < 580:
        # Green to Yellow
        r = (w - 510) / (580 - 510)
        g = 1.0
        b = 0.0
    elif 580 <= w < 645:
        # Yellow to Red
        r = 1.0
        g = -(w - 645) / (645 - 580)
        b = 0.0
    else:  # 645 <= w <= 780
        # Red
        r = 1.0
        g = 0.0
        b = 0.0

    # Intensity falloff at spectral extremes
    if w < 420:
        intensity = 0.3 + 0.7 * (w - 380) / (420 - 380)
    elif w > 645:
        intensity = 0.3 + 0.7 * (780 - w) / (780 - 645)
    else:
        intensity = 1.0

    r, g, b = r * intensity, g * intensity, b * intensity

    # Gamma correction for sRGB displays
    gamma = 0.8
    r = r**gamma if r > 0 else 0.0
    g = g**gamma if g > 0 else 0.0
    b = b**gamma if b > 0 else 0.0

    return (r, g, b)


def wavelength_to_hex(wavelength_nm: float) -> str:
    """Convert wavelength (nm) to hex color string."""
    r, g, b = wavelength_to_rgb(wavelength_nm)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color string to RGB tuple (0-255)."""
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB values (0-255) to hex color string."""
    return f"#{r:02x}{g:02x}{b:02x}"


def lighten_color(hex_color: str, factor: float = 0.4) -> str:
    """Create a lighter shade of a hex color."""
    r, g, b = hex_to_rgb(hex_color)
    new_r = int(r + (255 - r) * factor)
    new_g = int(g + (255 - g) * factor)
    new_b = int(b + (255 - b) * factor)
    return rgb_to_hex(new_r, new_g, new_b)


def darken_color(hex_color: str, factor: float = 0.4) -> str:
    """Create a darker shade of a hex color."""
    r, g, b = hex_to_rgb(hex_color)
    new_r = int(r * (1 - factor))
    new_g = int(g * (1 - factor))
    new_b = int(b * (1 - factor))
    return rgb_to_hex(new_r, new_g, new_b)
