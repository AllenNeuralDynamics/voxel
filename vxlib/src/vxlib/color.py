"""Color utilities and colormap registry for Voxel.

Provides a Color class for hex color manipulation and a registry of named
colormaps for fluorescence microscopy channels. Used by the preview system
to apply false-color LUTs to grayscale camera frames.

Usage:
    from vxlib.color import Color, resolve_colormap

    c = Color("#00ff00")
    c.rgb           # (0, 255, 0)
    c.rgb_float     # (0.0, 1.0, 0.0)
    c.lighten(0.2)  # Color("#33ff33")

    # Resolve a colormap by name or hex color
    lut = resolve_colormap("gfp")       # 256x3 numpy array
    lut = resolve_colormap("#ff0066")   # linear ramp to that color
    lut = resolve_colormap("inferno")   # gradient colormap
"""

from __future__ import annotations

import colorsys
from typing import Self

import numpy as np
from pydantic import BaseModel, RootModel, field_validator


class Color(str):
    """A color that behaves as a hex string but provides color manipulation methods.

    Initialization:
        Color("#3a6ea5")      # 6-digit hex with #
        Color("3a6ea5")       # 6-digit hex without #
        Color("#f00")         # 3-digit hex
        Color.from_rgb(58, 110, 165)
        Color.from_hsl(0.58, 0.48, 0.44)
        Color.from_wavelength(510.0)
    """

    __slots__ = ()

    def __new__(cls, value: str) -> Self:
        hex_str = cls._normalize_hex(value)
        return super().__new__(cls, hex_str)

    @staticmethod
    def _normalize_hex(value: str) -> str:
        """Convert various hex formats to #rrggbb."""
        h = value.lstrip("#").lower()
        if len(h) == 3:
            h = h[0] * 2 + h[1] * 2 + h[2] * 2
        if len(h) != 6:
            raise ValueError(f"Invalid hex color: {value}")
        return f"#{h}"

    # -- Properties -----------------------------------------------------------

    @property
    def rgb(self) -> tuple[int, int, int]:
        """RGB tuple with values 0-255."""
        h = self.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    @property
    def rgb_float(self) -> tuple[float, float, float]:
        """RGB tuple with values 0.0-1.0."""
        r, g, b = self.rgb
        return (r / 255, g / 255, b / 255)

    @property
    def hsl(self) -> tuple[float, float, float]:
        """HSL tuple (hue, saturation, lightness) with values 0.0-1.0."""
        r, g, b = self.rgb_float
        hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
        return (hue, saturation, lightness)

    @property
    def luminance(self) -> float:
        """Relative luminance (0.0-1.0) per WCAG formula."""
        r, g, b = self.rgb_float

        def linearize(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)

    # -- Modifiers (return new Color) -----------------------------------------

    def lighten(self, factor: float = 0.2) -> Color:
        """Return a lighter shade."""
        r, g, b = self.rgb
        return Color.from_rgb(
            int(r + (255 - r) * factor),
            int(g + (255 - g) * factor),
            int(b + (255 - b) * factor),
        )

    def darken(self, factor: float = 0.2) -> Color:
        """Return a darker shade."""
        r, g, b = self.rgb
        return Color.from_rgb(
            int(r * (1 - factor)),
            int(g * (1 - factor)),
            int(b * (1 - factor)),
        )

    def contrasting(self, light: str = "#ffffff", dark: str = "#000000") -> Color:
        """Return light or dark color based on contrast with this color."""
        return Color(dark if self.luminance > 0.179 else light)

    # -- Factory methods ------------------------------------------------------

    @classmethod
    def from_rgb(cls, r: int, g: int, b: int) -> Color:
        """Create from RGB values (0-255)."""
        return cls(f"#{r:02x}{g:02x}{b:02x}")

    @classmethod
    def from_hsl(cls, hue: float, saturation: float, lightness: float) -> Color:
        """Create from HSL values (0.0-1.0)."""
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        return cls.from_rgb(int(r * 255), int(g * 255), int(b * 255))

    @classmethod
    def from_wavelength(cls, wavelength_nm: float) -> Color:
        """Create from light wavelength in nanometers (380-780nm visible range).

        Uses gamma correction for better violet rendering on sRGB displays.
        Returns black if wavelength is outside visible range.
        """
        w = wavelength_nm

        if w < 380 or w > 780:
            return cls("#000000")

        if 380 <= w < 440:
            r, g, b = 0.6 * (1.0 - (w - 380) / (440 - 380)), 0.0, 1.0
        elif 440 <= w < 490:
            r, g, b = 0.0, (w - 440) / (490 - 440), 1.0
        elif 490 <= w < 510:
            r, g, b = 0.0, 1.0, -(w - 510) / (510 - 490)
        elif 510 <= w < 580:
            r, g, b = (w - 510) / (580 - 510), 1.0, 0.0
        elif 580 <= w < 645:
            r, g, b = 1.0, -(w - 645) / (645 - 580), 0.0
        else:  # 645 <= w <= 780
            r, g, b = 1.0, 0.0, 0.0

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

        return cls.from_rgb(int(r * 255), int(g * 255), int(b * 255))

    # -- LUT generation -------------------------------------------------------

    def to_lut(self, resolution: int = 256) -> np.ndarray:
        """Generate a linear LUT ramp from black to this color.

        Returns:
            numpy array of shape (resolution, 3) with dtype uint8.
        """
        r, g, b = self.rgb
        t = np.linspace(0.0, 1.0, resolution, dtype=np.float32)
        lut = np.zeros((resolution, 3), dtype=np.uint8)
        lut[:, 0] = np.round(r * t).astype(np.uint8)
        lut[:, 1] = np.round(g * t).astype(np.uint8)
        lut[:, 2] = np.round(b * t).astype(np.uint8)
        return lut


# =============================================================================
# Colormap
# =============================================================================


def _interpolate_stops(stops: list[tuple[int, int, int]], resolution: int) -> np.ndarray:
    """Interpolate between RGB color stops to produce a LUT."""
    n = len(stops)
    lut = np.zeros((resolution, 3), dtype=np.uint8)
    for i in range(resolution):
        t = i / (resolution - 1)
        seg = t * (n - 1)
        lo = min(int(seg), n - 2)
        hi = lo + 1
        frac = seg - lo
        r = int(stops[lo][0] + (stops[hi][0] - stops[lo][0]) * frac)
        g = int(stops[lo][1] + (stops[hi][1] - stops[lo][1]) * frac)
        b = int(stops[lo][2] + (stops[hi][2] - stops[lo][2]) * frac)
        lut[i] = (r, g, b)
    return lut


class Colormap(RootModel[str | list[str]]):
    """A colormap defined by a list of hex color stops.

    The LUT is generated by interpolating between stops. A single hex string
    is normalized to [black, color] on construction.

    Usage:
        Colormap(["#000000", "#00ff00"])   # explicit stops
        Colormap("#00ff00")                # shorthand for black → color
    """

    @field_validator("root", mode="before")
    @classmethod
    def _normalize(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return ["#000000", v]
        return v

    def to_lut(self, resolution: int = 256) -> np.ndarray:
        """Generate a LUT array of shape (resolution, 3) with dtype uint8."""
        colors = [self.root] if isinstance(self.root, str) else self.root
        stops = [Color(c).rgb for c in colors]
        return _interpolate_stops(stops, resolution)


# =============================================================================
# Colormap Catalog
# =============================================================================


class ColormapGroup(BaseModel):
    """A named group of colormaps."""

    uid: str
    label: str
    desc: str = ""
    colormaps: dict[str, Colormap]


_BASIC = ColormapGroup(
    uid="basic",
    label="Basic Colors",
    desc="Simple single-color ramps",
    colormaps={
        "red": Colormap("#ff0000"),
        "green": Colormap("#00ff00"),
        "blue": Colormap("#0000ff"),
        "cyan": Colormap("#00ffff"),
        "magenta": Colormap("#ff00ff"),
        "yellow": Colormap("#ffff00"),
        "orange": Colormap("#ffa500"),
        "white": Colormap("#ffffff"),
        "farred": Colormap("#aa0066"),
    },
)

_FLUORESCENT_PROTEINS = ColormapGroup(
    uid="fluorescent_proteins",
    label="Fluorescent Proteins",
    desc="Common genetically encoded fluorescent proteins",
    colormaps={
        "gfp": Colormap("#00ff00"),
        "egfp": Colormap("#00ff00"),
        "yfp": Colormap("#ffff00"),
        "eyfp": Colormap("#ffff00"),
        "citrine": Colormap("#ffff00"),
        "venus": Colormap("#ffff00"),
        "rfp": Colormap("#ff6600"),
        "dsred": Colormap("#ff0000"),
        "mcherry": Colormap("#ff0066"),
        "tdtomato": Colormap("#ff4500"),
        "mkate2": Colormap("#ff0033"),
        "cfp": Colormap("#00ffff"),
        "ecfp": Colormap("#00ffff"),
        "cerulean": Colormap("#00ccff"),
        "mplum": Colormap("#cc00ff"),
        "katushka": Colormap("#ff0066"),
    },
)

_NUCLEAR_STAINS = ColormapGroup(
    uid="nuclear_stains",
    label="Nuclear Stains",
    desc="DNA-binding fluorescent dyes",
    colormaps={
        "dapi": Colormap("#0066ff"),
        "hoechst": Colormap("#0066ff"),
        "draq5": Colormap("#aa0066"),
        "pi": Colormap("#ff0000"),
    },
)

_ALEXA_DYES = ColormapGroup(
    uid="alexa_dyes",
    label="Alexa Dyes",
    desc="Alexa Fluor conjugated dyes",
    colormaps={
        "alexa488": Colormap("#00ff99"),
        "alexa555": Colormap("#ffaa00"),
        "alexa594": Colormap("#ff6600"),
        "alexa647": Colormap("#ff0066"),
    },
)

_CY_DYES = ColormapGroup(
    uid="cy_dyes",
    label="Cy Dyes",
    desc="Cyanine family fluorescent dyes",
    colormaps={
        "cy3": Colormap("#ffaa00"),
        "cy5": Colormap("#ff0066"),
        "cy7": Colormap("#990033"),
    },
)

_ATTO_DYES = ColormapGroup(
    uid="atto_dyes",
    label="ATTO Dyes",
    desc="ATTO-TEC fluorescent labels",
    colormaps={
        "atto488": Colormap("#00ff99"),
        "atto565": Colormap("#ff9900"),
        "atto647n": Colormap("#ff0066"),
    },
)

_CLASSIC_FLUOROPHORES = ColormapGroup(
    uid="classic_fluorophores",
    label="Classic Fluorophores",
    desc="Traditional organic fluorescent dyes",
    colormaps={
        "fitc": Colormap("#00ff00"),
        "tritc": Colormap("#ff6600"),
        "rhodamine": Colormap("#ff0066"),
        "tamra": Colormap("#ffaa00"),
    },
)

_FUNCTIONAL_INDICATORS = ColormapGroup(
    uid="functional_indicators",
    label="Functional Indicators",
    desc="Activity-dependent fluorescent reporters",
    colormaps={
        "gcamp": Colormap("#00ff00"),
        "gcamp6": Colormap("#00ff00"),
        "gcamp7": Colormap("#00ff00"),
        "rhod2": Colormap("#ff0066"),
        "fluo4": Colormap("#00ff00"),
        "fluo8": Colormap("#00ff00"),
        "cal520": Colormap("#00ff99"),
        "asap": Colormap("#00ff99"),
        "asap3": Colormap("#00ff99"),
        "archer": Colormap("#00ff00"),
        "phrodo": Colormap("#ff0066"),
    },
)

_ORGANELLE_STAINS = ColormapGroup(
    uid="organelle_stains",
    label="Organelle Stains",
    desc="Membrane and organelle-selective dyes",
    colormaps={
        "dil": Colormap("#ff6600"),
        "dio": Colormap("#00ff00"),
        "mitotracker": Colormap("#ff0066"),
        "tmrm": Colormap("#ff6600"),
    },
)

_GRADIENTS = ColormapGroup(
    uid="gradients",
    label="Gradients",
    desc="Perceptually uniform and classic scientific colormaps",
    colormaps={
        "inferno": Colormap(["#000003", "#270b52", "#65156e", "#9e2963", "#d44841", "#f57c15", "#fac128", "#fcfea4"]),
        "viridis": Colormap(["#440154", "#46317e", "#365b8c", "#277e8e", "#1fa187", "#49c16d", "#9fd938", "#fde724"]),
        "magma": Colormap(["#000003", "#221150", "#5e177f", "#972c7f", "#d3426d", "#f8755c", "#febb80", "#fbfcbf"]),
        "plasma": Colormap(["#0c0786", "#5201a3", "#8b09a4", "#b83289", "#db5b67", "#f38748", "#fdbc2a", "#eff821"]),
        "cividis": Colormap(["#00224d", "#213b6e", "#4c546c", "#6c6d72", "#8d8978", "#b1a570", "#d8c45b", "#fde737"]),
        "turbo": Colormap(["#30123b", "#4675ed", "#1bcfd4", "#61fc6c", "#d1e834", "#fe9b2d", "#d93806", "#7a0402"]),
        "hot": Colormap(["#0a0000", "#690000", "#ca0000", "#ff2900", "#ff8a00", "#ffe900", "#ffff71", "#ffffff"]),
        "cool": Colormap(["#00ffff", "#24dbff", "#49b6ff", "#6d92ff", "#926dff", "#b649ff", "#db24ff", "#ff00ff"]),
        "coolwarm": Colormap(["#3a4cc0", "#6788ed", "#99bafe", "#c8d7ef", "#edd0c1", "#f6a789", "#e16852", "#b30326"]),
        "gray": Colormap(["#000000", "#242424", "#494949", "#6d6d6d", "#929292", "#b6b6b6", "#dbdbdb", "#ffffff"]),
        "grayscale": Colormap(["#000000", "#242424", "#494949", "#6d6d6d", "#929292", "#b6b6b6", "#dbdbdb", "#ffffff"]),
        "bone": Colormap(["#000000", "#1f1f2b", "#3f3f58", "#5f647f", "#7f919f", "#9fbcbf", "#cddfdf", "#ffffff"]),
        "copper": Colormap(["#000000", "#2c1c11", "#5a3924", "#865536", "#b47248", "#e08e5a", "#ffab6c", "#ffc77e"]),
        "jet": Colormap(["#00007f", "#0010ff", "#00a4ff", "#3fffb7", "#b7ff3f", "#ffb900", "#ff3000", "#7f0000"]),
    },
)

COLORMAP_CATALOG: list[ColormapGroup] = [
    _BASIC,
    _FLUORESCENT_PROTEINS,
    _NUCLEAR_STAINS,
    _ALEXA_DYES,
    _CY_DYES,
    _ATTO_DYES,
    _CLASSIC_FLUOROPHORES,
    _FUNCTIONAL_INDICATORS,
    _ORGANELLE_STAINS,
    _GRADIENTS,
]

# Flat lookup: name → Colormap object (built from catalog)
_COLORMAP_INDEX: dict[str, Colormap] = {
    name: cmap for group in COLORMAP_CATALOG for name, cmap in group.colormaps.items()
}


def resolve_colormap(name: str, resolution: int = 256) -> np.ndarray:
    """Resolve a colormap name or hex color to a LUT array (resolution, 3) uint8."""
    key = name.strip().lower()
    cmap = _COLORMAP_INDEX.get(key)
    if cmap is not None:
        return cmap.to_lut(resolution)
    return Colormap(key).to_lut(resolution)


def get_colormap_catalog() -> list[ColormapGroup]:
    """Return the complete colormap catalog."""
    return COLORMAP_CATALOG
