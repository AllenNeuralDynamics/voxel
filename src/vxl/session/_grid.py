"""Grid and tiling utilities for Voxel sessions."""

import logging
import math

from vxl.config import GridConfig
from vxl.stack import Tile

log = logging.getLogger(__name__)


def compute_tiles(
    gc: GridConfig,
    fov: tuple[float, float],
    stage_bounds: tuple[float, float, float, float],
) -> list[Tile]:
    """Generate the tile grid based on grid config, FOV, and stage bounds.

    Args:
        gc: Grid configuration (offset, overlap, z defaults).
        fov: Current FOV (width, height) in µm.
        stage_bounds: (x_lower, x_upper, y_lower, y_upper) in µm.

    Tile positions are CENTER-ANCHORED: (x, y) represents the center of each tile.

    Returns:
        List of Tile objects covering the stage area from the grid offset.
    """
    fov_w, fov_h = fov
    step_w = fov_w * (1 - gc.overlap_x)
    step_h = fov_h * (1 - gc.overlap_y)

    x_lower, x_upper, y_lower, y_upper = stage_bounds
    stage_width = x_upper - x_lower
    stage_height = y_upper - y_lower

    offset_x = gc.x_offset
    offset_y = gc.y_offset

    col_min = math.ceil(-offset_x / step_w) if step_w > 0 else 0
    col_max = math.floor((stage_width - offset_x) / step_w) + 1 if step_w > 0 else 1
    row_min = math.ceil(-offset_y / step_h) if step_h > 0 else 0
    row_max = math.floor((stage_height - offset_y) / step_h) + 1 if step_h > 0 else 1

    tiles: list[Tile] = []
    for row in range(row_min, row_max):
        for col in range(col_min, col_max):
            tx = offset_x + col * step_w
            ty = offset_y + row * step_h

            if 0 <= tx <= stage_width and 0 <= ty <= stage_height:
                tile_id = f"tile_r{row}_c{col}"
                tiles.append(
                    Tile(
                        tile_id=tile_id,
                        row=row,
                        col=col,
                        x=tx,
                        y=ty,
                        w=fov_w,
                        h=fov_h,
                    ),
                )

    num_cols = col_max - col_min
    num_rows = row_max - row_min
    log.debug(
        "Generated %d tiles (%dx%d) with FOV %.0fx%.0f um, step %.0fx%.0f um",
        len(tiles),
        num_cols,
        num_rows,
        fov_w,
        fov_h,
        step_w,
        step_h,
    )
    return tiles
