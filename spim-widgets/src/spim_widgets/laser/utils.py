def wavelength_to_rgb(wavelength_nm: float) -> tuple[float, float, float]:
    """Approximate monochromatic wavelength (nm) -> linear-ish RGB in [0,1].

    This version is based on the common piecewise spectral-to-RGB approximation
    but corrects the violet range to avoid appearing magenta. It also improves
    the intensity falloff at the spectral extremes.

    Returns (0,0,0) if the wavelength is outside the visible range of ~380-780 nm.
    """
    w = wavelength_nm

    # Check if the wavelength is outside the visible spectrum
    if w < 380 or w > 780:
        return (0.0, 0.0, 0.0)

    # Calculate the raw RGB values based on the wavelength
    if 380 <= w < 440:
        # Violet to Blue
        # The red component is decreased to avoid magenta
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

    # Adjust intensity to simulate human eye sensitivity falloff at the extremes
    if w < 420:
        intensity = 0.3 + 0.7 * (w - 380) / (420 - 380)
    elif w > 645:
        intensity = 0.3 + 0.7 * (780 - w) / (780 - 645)
    else:
        intensity = 1.0

    r, g, b = r * intensity, g * intensity, b * intensity

    # Apply a gentle gamma correction to look better on sRGB displays
    gamma = 0.8
    r = r**gamma if r > 0 else 0.0
    g = g**gamma if g > 0 else 0.0
    b = b**gamma if b > 0 else 0.0

    return (r, g, b)


def rgb_to_css_string(rgb: tuple[float, float, float], alpha: float = 1.0) -> str:
    """Converts an RGB tuple (with values from 0.0 to 1.0) to a CSS rgba string.

    Args:
        rgb: A tuple containing the red, green, and blue components.
        alpha: An optional alpha value for transparency (0.0 to 1.0).

    Returns:
        A CSS rgba string, e.g., "rgba(255, 0, 128, 0.5)".
    """
    # Unpack the tuple and scale values from [0,1] to [0,255]
    r, g, b = rgb
    r_int = int(r * 255)
    g_int = int(g * 255)
    b_int = int(b * 255)

    # Format the CSS string
    return f'rgba({r_int}, {g_int}, {b_int}, {alpha})'


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Converts RGB tuple to a hex string."""
    return f'#{r:02x}{g:02x}{b:02x}'


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Converts a hex color string to an RGB tuple."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b)


def lighten_color(r: int, g: int, b: int, factor: float = 0.4) -> tuple[int, int, int]:
    """Creates a lighter shade of a color."""
    white_r, white_g, white_b = 255, 255, 255
    new_r = int(r + (white_r - r) * factor)
    new_g = int(g + (white_g - g) * factor)
    new_b = int(b + (white_b - b) * factor)
    return (new_r, new_g, new_b)


def darken_color(r: int, g: int, b: int, factor: float = 0.4) -> tuple[int, int, int]:
    """Creates a darker shade of a color."""
    black_r, black_g, black_b = 0, 0, 0
    new_r = int(r + (black_r - r) * factor)
    new_g = int(g + (black_g - g) * factor)
    new_b = int(b + (black_b - b) * factor)
    return (new_r, new_g, new_b)


def lighten_hex_color(hex_color: str, factor: float = 0.4) -> str:
    """Creates a lighter shade of a hex color."""
    rgb = hex_to_rgb(hex_color)
    new_rgb = lighten_color(*rgb, factor=factor)
    return rgb_to_hex(*new_rgb)
