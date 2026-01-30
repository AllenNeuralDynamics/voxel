# /// script
# requires-python = ">=3.13"
# dependencies = ["matplotlib"]
# ///
"""Sample matplotlib colormaps into hex color stops.

Usage:
    uv run vxlib/generate_gradients.py
    uv run vxlib/generate_gradients.py --stops 12
    uv run vxlib/generate_gradients.py --names inferno viridis magma
"""

from __future__ import annotations

import argparse

import numpy as np
from matplotlib.pyplot import get_cmap

DEFAULT_NAMES = [
    "inferno",
    "viridis",
    "magma",
    "plasma",
    "cividis",
    "turbo",
    "hot",
    "cool",
    "coolwarm",
    "gray",
    "bone",
    "copper",
    "jet",
]


def sample_colormap(name: str, n_stops: int) -> list[str]:
    """Sample a matplotlib colormap into a list of hex color strings."""
    cmap = get_cmap(name)
    t = np.linspace(0.0, 1.0, n_stops)
    rgba = cmap(t)
    return [f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}" for r, g, b, _a in rgba]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample matplotlib colormaps into hex stops")
    parser.add_argument("--stops", type=int, default=8, help="Number of color stops (default: 8)")
    parser.add_argument("--names", nargs="+", default=DEFAULT_NAMES, help="Colormap names to sample")
    args = parser.parse_args()

    for name in args.names:
        stops = sample_colormap(name, args.stops)
        colors = ", ".join(f'"{s}"' for s in stops)
        print(f'Colormap(name="{name}", colors=[{colors}]),')


if __name__ == "__main__":
    main()
