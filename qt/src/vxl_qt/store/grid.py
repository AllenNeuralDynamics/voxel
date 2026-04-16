"""Grid state store for Voxel application.

This module provides centralized management of grid/tile/stack state,
enabling reactive UI updates when grid configuration or selection changes.
"""

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from vxl.config import GridConfig, PlanConfig
from vxl.stack import Stack, StackOrder, StackStatus
from vxl_qt.tile import Tile

if TYPE_CHECKING:
    from vxl import Session

log = logging.getLogger(__name__)


@dataclass
class LayerVisibility:
    """Visibility state for grid canvas layers."""

    grid: bool = True
    stacks: bool = True
    path: bool = True
    fov: bool = True


# Status colors for stacks (matching studio)
STACK_STATUS_COLORS: dict[StackStatus | None, str] = {
    StackStatus.PLANNED: "#3a6ea5",  # blue (ACCENT)
    StackStatus.ACQUIRING: "#22d3ee",  # cyan-400
    StackStatus.COMPLETED: "#4ec9b0",  # teal (SUCCESS)
    StackStatus.FAILED: "#f44336",  # red (ERROR)
    StackStatus.SKIPPED: "#ffb74d",  # orange (WARNING)
    None: "#71717a",  # zinc-500 (no stack)
}


def _generate_tiles(gc: GridConfig, fov_size: tuple[float, float], stage_w: float, stage_h: float) -> list[Tile]:
    """Generate tile grid from grid config, FOV size, and stage dimensions."""
    fov_w, fov_h = fov_size
    step_w = fov_w * (1 - gc.overlap_x)
    step_h = fov_h * (1 - gc.overlap_y)
    if step_w <= 0 or step_h <= 0 or stage_w <= 0 or stage_h <= 0:
        return []

    col_min = math.ceil(-gc.x_offset / step_w)
    col_max = math.floor((stage_w - gc.x_offset) / step_w) + 1
    row_min = math.ceil(-gc.y_offset / step_h)
    row_max = math.floor((stage_h - gc.y_offset) / step_h) + 1

    tiles: list[Tile] = []
    for row in range(row_min, row_max):
        for col in range(col_min, col_max):
            tx = gc.x_offset + col * step_w
            ty = gc.y_offset + row * step_h
            if 0 <= tx <= stage_w and 0 <= ty <= stage_h:
                tiles.append(Tile(tile_id=f"tile_r{row}_c{col}", row=row, col=col, x=tx, y=ty, w=fov_w, h=fov_h))
    return tiles


def get_stack_status_color(status: StackStatus | None) -> str:
    """Get the color for a stack status."""
    return STACK_STATUS_COLORS.get(status, STACK_STATUS_COLORS[None])


class GridStore(QObject):
    """Manages grid state with Qt signals for reactive UI updates.

    This store wraps the Session's grid/tile/stack management and provides
    Qt signals for UI components to react to state changes.

    Usage:
        store = GridStore()

        # Bind to session when ready
        await store.bind_session(session)

        # Connect to signals
        store.tiles_changed.connect(on_tiles_updated)
        store.selection_changed.connect(on_selection_changed)

        # Select a tile
        store.select_tile(2, 3)

        # Modify grid (async operations)
        fire_and_forget(store.set_grid_offset(100.0, 50.0))
    """

    # Signals
    tiles_changed = Signal()  # Tile grid regenerated
    stacks_changed = Signal()  # Stacks list modified
    grid_config_changed = Signal()  # Offset, overlap, or z_step changed
    selection_changed = Signal(int, int)  # row, col of selected tile
    layer_visibility_changed = Signal()
    grid_locked_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session: Session | None = None
        self._tiles: list[Tile] = []
        self._fov_size: tuple[float, float] | None = None

        # Local UI state
        self._selected_row: int = 0
        self._selected_col: int = 0
        self._layer_visibility = LayerVisibility()

    # ==================== Session Binding ====================

    async def bind_session(self, session: "Session") -> None:
        """Bind to a session and refresh tiles.

        Called from VoxelApp after session is ready.
        """
        self._session = session
        self._fov_size = None
        await self.refresh_tiles()
        log.info("GridStore bound to session")

    def unbind_session(self) -> None:
        """Unbind from session and clear state."""
        self._session = None
        self._tiles = []
        self._fov_size = None
        self._selected_row = 0
        self._selected_col = 0
        self.tiles_changed.emit()
        self.stacks_changed.emit()
        log.info("GridStore unbound from session")

    @property
    def is_bound(self) -> bool:
        """Whether the store is bound to a session."""
        return self._session is not None

    # ==================== Properties (backed by Session) ====================

    @property
    def tiles(self) -> list[Tile]:
        """Cached list of tiles. Refreshed on config change."""
        return self._tiles

    @property
    def stacks(self) -> list[Stack]:
        """List of stacks from session."""
        if self._session is None:
            return []
        return list(self._session.stacks)

    @property
    def grid_config(self) -> GridConfig:
        """Current grid configuration."""
        if self._session is None:
            return GridConfig()
        return self._session.config.grid

    @property
    def plan_config(self) -> PlanConfig:
        """Current plan configuration (z_step, default Z range, stack ordering, etc.)."""
        if self._session is None:
            return PlanConfig()
        return self._session.config.plan

    @property
    def stack_order(self) -> StackOrder:
        """Current stack ordering strategy."""
        if self._session is None:
            return StackOrder.SNAKE_ROW
        return self._session.config.plan.stack_order

    @property
    def grid_locked(self) -> bool:
        """Whether grid is locked (stacks exist for the active profile)."""
        if self._session is None:
            return False
        active_pid = self._session.microscope.profiles.active_id
        return any(s.profile_id == active_pid for s in self._session.stacks)

    @property
    def fov_size(self) -> tuple[float, float]:
        """Cached FOV size in µm (width, height)."""
        if self._fov_size is None:
            return (5000.0, 5000.0)  # Default 5mm x 5mm
        return self._fov_size

    # ==================== Local UI State ====================

    @property
    def selected_row(self) -> int:
        """Currently selected tile row."""
        return self._selected_row

    @property
    def selected_col(self) -> int:
        """Currently selected tile column."""
        return self._selected_col

    @property
    def layer_visibility(self) -> LayerVisibility:
        """Layer visibility state."""
        return self._layer_visibility

    # ==================== Selection ====================

    def select_tile(self, row: int, col: int) -> None:
        """Select a tile by row and column."""
        if self._selected_row != row or self._selected_col != col:
            self._selected_row = row
            self._selected_col = col
            self.selection_changed.emit(row, col)

    def get_selected_tile(self) -> Tile | None:
        """Get the currently selected tile, or None if not found."""
        for tile in self._tiles:
            if tile.row == self._selected_row and tile.col == self._selected_col:
                return tile
        return None

    def get_selected_stack(self) -> Stack | None:
        """Get the stack at the selected tile, or None if no stack."""
        tile = self.get_selected_tile()
        if tile is None:
            return None
        return self.get_stack_at_position(tile.x, tile.y)

    def get_stack_at_position(self, x: float, y: float) -> Stack | None:
        """Get the stack near a specific position (within 0.1 µm tolerance)."""
        for stack in self.stacks:
            if abs(stack.x - x) < 0.1 and abs(stack.y - y) < 0.1:
                return stack
        return None

    # ==================== Grid Config Methods ====================

    async def refresh_tiles(self) -> None:
        """Refresh the tile grid from session.

        Generates tiles locally from grid config + FOV size (same algorithm as the web frontend).
        """
        if self._session is None:
            self._tiles = []
            self._fov_size = None
        else:
            try:
                fov = self._session.microscope.profiles.fov
            except (ValueError, KeyError):
                fov = None
            if fov is None:
                self._tiles = []
                self._fov_size = None
            else:
                try:
                    self._fov_size = fov
                    stage = self._session.microscope.stage
                    x_lo = await stage.x.get_lower_limit()
                    x_hi = await stage.x.get_upper_limit()
                    y_lo = await stage.y.get_lower_limit()
                    y_hi = await stage.y.get_upper_limit()
                    self._tiles = _generate_tiles(
                        self._session.config.grid, self._fov_size, stage_w=x_hi - x_lo, stage_h=y_hi - y_lo
                    )
                except (ValueError, KeyError):
                    self._tiles = []
                    self._fov_size = None

        self.tiles_changed.emit()
        log.debug("Tiles refreshed: %d tiles", len(self._tiles))

    async def set_grid_offset(self, x_um: float, y_um: float) -> None:
        """Set grid offset in micrometers."""
        if self._session is None:
            return
        if self.grid_locked:
            log.warning("Cannot modify grid: acquisition has started")
            return

        grid = self._session.config.grid
        grid.x_offset = x_um
        grid.y_offset = y_um
        await self.refresh_tiles()
        self.grid_config_changed.emit()
        self.stacks_changed.emit()  # Stack positions may have changed

    async def set_overlap(self, overlap_x: float, overlap_y: float) -> None:
        """Set tile overlap (0.0 to <1.0)."""
        if self._session is None:
            return
        if self.grid_locked:
            log.warning("Cannot modify grid: acquisition has started")
            return

        grid = self._session.config.grid
        grid.overlap_x = overlap_x
        grid.overlap_y = overlap_y
        await self.refresh_tiles()
        self.grid_config_changed.emit()
        self.stacks_changed.emit()  # Stack positions may have changed

    def set_stack_order(self, order: StackOrder) -> None:
        """Set stack ordering strategy."""
        if self._session is None:
            return
        self._session.stacks.update_order(stack_order=order)
        self.stacks_changed.emit()  # Stack order changed

    # ==================== Stack Management ====================

    async def add_stacks(self, stacks: list[dict]) -> list[Stack]:
        """Add stacks at positions.

        Args:
            stacks: List of {x, y, z_start, z_end}

        Returns:
            List of added Stack objects
        """
        if self._session is None:
            return []

        added = self._session.stacks.add(stacks)
        self.stacks_changed.emit()
        return added

    def edit_stacks(self, edits: list[dict]) -> list[Stack]:
        """Edit stacks' position and/or z parameters.

        Args:
            edits: List of {stack_id, x?, y?, z_start?, z_end?}

        Returns:
            List of edited Stack objects
        """
        if self._session is None:
            return []

        edited = self._session.stacks.edit(edits)
        self.stacks_changed.emit()
        return edited

    def remove_stacks(self, stack_ids: list[str]) -> None:
        """Remove stacks by ID."""
        if self._session is None:
            return

        self._session.stacks.remove(stack_ids)
        self.stacks_changed.emit()

    # ==================== Layer Visibility ====================

    def set_layer_visibility(self, layer: str, visible: bool) -> None:
        """Set visibility for a layer.

        Args:
            layer: One of 'grid', 'stacks', 'path', 'fov'
            visible: Whether the layer should be visible
        """
        if hasattr(self._layer_visibility, layer):
            setattr(self._layer_visibility, layer, visible)
            self.layer_visibility_changed.emit()

    def toggle_layer(self, layer: str) -> None:
        """Toggle visibility for a layer."""
        if hasattr(self._layer_visibility, layer):
            current = getattr(self._layer_visibility, layer)
            setattr(self._layer_visibility, layer, not current)
            self.layer_visibility_changed.emit()
