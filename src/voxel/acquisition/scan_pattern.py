from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from matplotlib import pyplot as plt

from voxel.utils.vec import Vec2D


class ScanPattern(StrEnum):
    RASTER = "raster"
    SERPENTINE = "serpentine"
    SPIRAL = "spiral"


class ScanDirection(StrEnum):
    ROW_WISE = "row_wise"
    COLUMN_WISE = "column_wise"


class StartCorner(StrEnum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


@dataclass
class ScanPathSettings:
    pattern: ScanPattern
    direction: ScanDirection
    start_corner: StartCorner
    reverse: bool


def generate_raster_path(grid_size: Vec2D[int], direction: ScanDirection) -> list[Vec2D]:
    path = []
    for y in range(grid_size.y):
        for x in range(grid_size.x):
            path.append(Vec2D(x, y))
    return path if direction == ScanDirection.ROW_WISE else _transpose_path(path)


def generate_serpentine_path(grid_size: Vec2D[int], direction: ScanDirection) -> list[Vec2D]:
    path = []
    for y in range(grid_size.y):
        row = [Vec2D(x, y) for x in range(grid_size.x)]
        if y % 2 == 1:
            row.reverse()
        path.extend(row)
    return path if direction == ScanDirection.ROW_WISE else _transpose_path(path)


def generate_spiral_path(grid_size: Vec2D[int]) -> list[Vec2D]:
    path = []
    x, y = 0, 0
    dx, dy = 1, 0
    for _ in range(grid_size.x * grid_size.y):
        if 0 <= x < grid_size.x and 0 <= y < grid_size.y:
            path.append(Vec2D(x, y))
        if x + dx == grid_size.x or x + dx < 0 or y + dy == grid_size.y or y + dy < 0 or Vec2D(x + dx, y + dy) in path:
            dx, dy = -dy, dx
        x, y = x + dx, y + dy
    return path


def _transpose_path(path: list[Vec2D[int]]) -> list[Vec2D[int]]:
    return [Vec2D(p.y, p.x) for p in path]


def adjust_for_start_corner(path: list[Vec2D], grid_size: Vec2D, start_corner: StartCorner) -> list[Vec2D]:
    match start_corner:
        case StartCorner.TOP_LEFT:
            return path
        case StartCorner.TOP_RIGHT:
            return [Vec2D(grid_size.x - 1 - p.x, p.y) for p in path]
        case StartCorner.BOTTOM_LEFT:
            return [Vec2D(p.x, grid_size.y - 1 - p.y) for p in path]
        case StartCorner.BOTTOM_RIGHT:
            return [Vec2D(grid_size.x - 1 - p.x, grid_size.y - 1 - p.y) for p in path]


def plot_scan_path(scan_path: list[Vec2D], title: str):
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_title(title)

    x = [point.x for point in scan_path]
    y = [point.y for point in scan_path]

    # Create a colormap based on the order of tiles
    # colors = plt.cm.viridis(np.linspace(0, 1, len(scan_path)))
    colors = plt.cm.get_cmap("viridis")(np.linspace(0, 1, len(scan_path)))

    # Plot tiles
    scatter = ax.scatter(x, y, c=range(len(scan_path)), cmap="viridis", s=100)

    # Add colorbar
    plt.colorbar(scatter, label="Scan Order")

    # Plot arrows to show the path direction
    for i in range(len(scan_path) - 1):
        ax.annotate(
            "",
            xy=(x[i + 1], y[i + 1]),
            xytext=(x[i], y[i]),
            arrowprops={"arrowstyle": "->", "color": colors[i], "lw": 1.5},
            va="center",
            ha="center",
        )

    # Highlight start and end points
    ax.plot(x[0], y[0], "go", markersize=15, label="Start")
    ax.plot(x[-1], y[-1], "ro", markersize=15, label="End")

    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.legend()

    # Invert y-axis to match the typical image coordinate system
    ax.invert_yaxis()

    plt.tight_layout()
    plt.show()
