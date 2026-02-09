"""Grid panel for acquisition grid display and control."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QWidget

from vxl.tile import Stack, Tile
from vxl_qt.store import (
    STACK_STATUS_COLORS,
    GridStore,
    PreviewStore,
    StageStore,
    composite_rgb,
    get_stack_status_color,
    resize_image,
)
from vxl_qt.ui.kit import (
    Colors,
    ColumnType,
    ControlSize,
    DoubleSpinBox,
    Field,
    Flex,
    GridFormBuilder,
    Select,
    Separator,
    Spacing,
    SpinBox,
    Stretch,
    Table,
    TableColumn,
    TableModel,
    Text,
    ToolButton,
    vbox,
)
from vxlib import fire_and_forget

if TYPE_CHECKING:
    from PySide6.QtGui import QPaintEvent, QResizeEvent

    from vxl.config import TileOrder

log = logging.getLogger(__name__)


# Status colors for table column (string keys from status.value)
_STATUS_COLORS_STR = {status.value: color for status, color in STACK_STATUS_COLORS.items() if status is not None}

# Tile order options for the Select widget
TILE_ORDER_OPTIONS: list[tuple[TileOrder, str]] = [
    ("row_wise", "Row-wise"),
    ("column_wise", "Column-wise"),
    ("snake_row", "Snake (Row)"),
    ("snake_column", "Snake (Column)"),
]

# Filter options for the grid table
GRID_FILTER_OPTIONS: list[tuple[str, str]] = [
    ("all", "All"),
    ("with_stack", "With Stack"),
    ("without_stack", "Without Stack"),
]

# Column definitions for the grid table
GRID_TABLE_COLUMNS: list[TableColumn] = [
    TableColumn(
        key="tile",
        header="Tile",
        width=70,
        getter=lambda t, _s: f"R{t.row}, C{t.col}",
    ),
    TableColumn(
        key="position",
        header="Position",
        width=None,  # Stretch to fill available space
        min_width=100,
        getter=lambda t, _s: f"{t.x_um / 1000:.2f}, {t.y_um / 1000:.2f}",
    ),
    TableColumn(
        key="z_start",
        header="Z Start",
        column_type=ColumnType.SPINBOX,
        width=90,
        getter=lambda _t, s: int(s.z_start_um) if s else 0,
        setter=lambda t, _s, v: {"row": t.row, "col": t.col, "z_start_um": v},
        editable=lambda _t, s: s is not None,
        suffix=" µm",
        min_val=-100000,
        max_val=100000,
        step=10,
    ),
    TableColumn(
        key="z_end",
        header="Z End",
        column_type=ColumnType.SPINBOX,
        width=90,
        getter=lambda _t, s: int(s.z_end_um) if s else 0,
        setter=lambda t, _s, v: {"row": t.row, "col": t.col, "z_end_um": v},
        editable=lambda _t, s: s is not None,
        suffix=" µm",
        min_val=-100000,
        max_val=100000,
        step=10,
    ),
    TableColumn(
        key="slices",
        header="Slices",
        width=55,
        getter=lambda _t, s: str(s.num_frames) if s else "—",
        align="right",
    ),
    TableColumn(
        key="profile",
        header="Profile",
        width=70,
        getter=lambda _t, s: s.profile_id if s else "—",
    ),
    TableColumn(
        key="status",
        header="Status",
        column_type=ColumnType.STATUS,
        width=75,
        getter=lambda _t, s: s.status.value if s and s.status else "",
        status_colors=_STATUS_COLORS_STR,
    ),
]


class GridTableModel(TableModel[Tile, Stack | None]):
    """Model for the grid table, backed by GridStore."""

    def __init__(self, store: GridStore, columns: list[TableColumn]) -> None:
        super().__init__(columns)
        self._store = store
        self._filter_mode = "all"

        # Connect to store signals
        self._store.tiles_changed.connect(self.refresh)
        self._store.stacks_changed.connect(self.refresh)

    def _get_rows(self) -> list[Tile]:
        """Get tiles, optionally filtered."""
        tiles = self._store.tiles
        if self._filter_mode == "with_stack":
            return [t for t in tiles if self._store.get_stack_at(t.row, t.col)]
        if self._filter_mode == "without_stack":
            return [t for t in tiles if not self._store.get_stack_at(t.row, t.col)]
        return tiles

    def _get_aux_data(self, row_data: Tile) -> Stack | None:
        """Get stack for a tile."""
        return self._store.get_stack_at(row_data.row, row_data.col)

    def _on_edit(self, row_data: Tile, aux_data: Stack | None, column: TableColumn, value: Any) -> None:
        """Handle inline editing."""
        if aux_data and column.setter:
            edit_dict = column.setter(row_data, aux_data, value)
            self._store.edit_stacks([edit_dict])

    def set_filter(self, mode: str) -> None:
        """Set the filter mode and refresh."""
        self._filter_mode = mode
        self.refresh()


class GridTable(QWidget):
    """Grid table with bulk operations.

    Features:
    - Multi-select via Shift+click and Ctrl+click
    - Inline Z-range editing
    - Row click syncs selection
    - Double-click for stage move
    """

    row_selected = Signal(int, int)  # row, col
    row_double_clicked = Signal(int, int)  # row, col (for stage move)
    selection_changed = Signal(int)  # count of selected items

    def __init__(self, store: GridStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = vbox(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Table
        self._model = GridTableModel(self._store, GRID_TABLE_COLUMNS)
        self._table = Table(model=self._model, columns=GRID_TABLE_COLUMNS)
        layout.addWidget(self._table)

    def _connect_signals(self) -> None:
        self._table.row_clicked.connect(self._on_row_clicked)
        self._table.row_double_clicked.connect(self._on_row_double_clicked)
        self._table.selection_changed.connect(self._on_selection_changed)

    def set_filter(self, mode: str) -> None:
        """Set the filter mode from external source."""
        self._model.set_filter(mode)

    def get_selected_tiles(self) -> list[Tile]:
        """Get list of selected tiles."""
        rows = self._table.get_selected_rows()
        return [t for idx in rows if (t := self._model.get_row_at(idx)) is not None]

    def delete_selected(self) -> None:
        """Delete stacks for all selected tiles."""
        tiles = self.get_selected_tiles()
        positions = [{"row": t.row, "col": t.col} for t in tiles]
        if positions:
            self._store.remove_stacks(positions)
            self._table.clear_selection()

    def clear_selection(self) -> None:
        """Clear table selection."""
        self._table.clear_selection()

    def _on_row_clicked(self, row_idx: int) -> None:
        """Handle row click - sync store selection to first selected."""
        tile = self._model.get_row_at(row_idx)
        if tile:
            self._store.select_tile(tile.row, tile.col)
            self.row_selected.emit(tile.row, tile.col)

    def _on_row_double_clicked(self, row_idx: int) -> None:
        """Handle row double-click - emit for stage move."""
        tile = self._model.get_row_at(row_idx)
        if tile:
            self.row_double_clicked.emit(tile.row, tile.col)

    def _on_selection_changed(self) -> None:
        """Handle row selection change."""
        self.selection_changed.emit(self._table.get_selected_count())


# =============================================================================
# Property Editors - Modular widgets for editing specific tile properties
# =============================================================================


class PropertyEditor(QWidget):
    """Base class for property editors.

    Property editors handle editing a specific property for one or more tiles.
    They provide a consistent interface for:
    - Displaying the edit form
    - Loading values from a tile/stack
    - Applying changes to tiles
    """

    # Emitted when value changes (for auto-save in single mode)
    value_changed = Signal()

    def __init__(self, store: GridStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._updating = False

    def load_from_tile(self, _tile: Tile, _stack: Stack | None) -> None:
        """Load values from a single tile/stack for display."""
        raise NotImplementedError

    def load_defaults(self) -> None:
        """Load default values (for multi-select or new stacks)."""
        raise NotImplementedError

    def apply_to_tiles(self, _tiles: list[Tile]) -> None:
        """Apply current values to the given tiles."""
        raise NotImplementedError


class ZRangeEditor(PropertyEditor):
    """Editor for Z range (z_start, z_end) property."""

    def __init__(self, store: GridStore, parent: QWidget | None = None) -> None:
        super().__init__(store, parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = vbox(self, spacing=Spacing.XS)
        layout.setContentsMargins(0, 0, 0, 0)

        self._z_start_spin = SpinBox(value=0, min_val=-100000, max_val=100000, step=10, size=ControlSize.SM)
        self._z_start_spin.setSuffix(" µm")

        self._z_end_spin = SpinBox(value=100, min_val=-100000, max_val=100000, step=10, size=ControlSize.SM)
        self._z_end_spin.setSuffix(" µm")

        self._slices_label = Text.muted("0")

        form = (
            GridFormBuilder(columns=2, spacing=Spacing.SM)
            .row(Field("Z Start", self._z_start_spin), Field("Z End", self._z_end_spin))
            .row(Field("Slices", self._slices_label))
            .build()
        )
        layout.addWidget(form)

    def _connect_signals(self) -> None:
        self._z_start_spin.valueChanged.connect(self._on_value_changed)
        self._z_end_spin.valueChanged.connect(self._on_value_changed)

    def _on_value_changed(self) -> None:
        if not self._updating:
            self._update_slices_display()
            self.value_changed.emit()

    def _update_slices_display(self) -> None:
        """Update the slices count based on current Z values."""
        z_step = self._store.grid_config.z_step_um
        if z_step > 0:
            z_range = abs(self._z_end_spin.value() - self._z_start_spin.value())
            slices = int(z_range / z_step) + 1
            self._slices_label.setText(str(slices))

    def load_from_tile(self, _tile: Tile, _stack: Stack | None) -> None:
        """Load Z range from tile's stack."""
        self._updating = True
        if _stack:
            self._z_start_spin.setValue(int(_stack.z_start_um))
            self._z_end_spin.setValue(int(_stack.z_end_um))
            self._slices_label.setText(str(_stack.num_frames))
        else:
            self.load_defaults()
        self._updating = False

    def load_defaults(self) -> None:
        """Load default Z range from grid config."""
        self._updating = True
        config = self._store.grid_config
        self._z_start_spin.setValue(int(config.default_z_start_um))
        self._z_end_spin.setValue(int(config.default_z_end_um))
        self._update_slices_display()
        self._updating = False

    def get_values(self) -> tuple[int, int]:
        """Get current Z range values."""
        return self._z_start_spin.value(), self._z_end_spin.value()

    def apply_to_tiles(self, _tiles: list[Tile]) -> None:
        """Apply Z range to all given tiles."""
        z_start, z_end = self.get_values()

        tiles_with_stacks = [t for t in _tiles if self._store.get_stack_at(t.row, t.col)]
        tiles_without_stacks = [t for t in _tiles if not self._store.get_stack_at(t.row, t.col)]

        if tiles_with_stacks:
            edit_dicts = [
                {"row": t.row, "col": t.col, "z_start_um": z_start, "z_end_um": z_end} for t in tiles_with_stacks
            ]
            self._store.edit_stacks(edit_dicts)

        if tiles_without_stacks:
            add_dicts = [
                {"row": t.row, "col": t.col, "z_start_um": z_start, "z_end_um": z_end} for t in tiles_without_stacks
            ]
            fire_and_forget(self._store.add_stacks(add_dicts), log=log)


class ProfileEditor(PropertyEditor):
    """Editor for profile property."""

    def __init__(self, store: GridStore, parent: QWidget | None = None) -> None:
        super().__init__(store, parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = vbox(self, spacing=Spacing.XS)
        layout.setContentsMargins(0, 0, 0, 0)

        # TODO: Add profile selector when profiles are available from store
        self._placeholder = Text.muted("Profile editing coming soon")
        layout.addWidget(self._placeholder)

    def load_from_tile(self, _tile: Tile, _stack: Stack | None) -> None:
        """Load profile from tile's stack."""
        # TODO: Implement when profiles are available

    def load_defaults(self) -> None:
        """Load default profile."""
        # TODO: Implement when profiles are available

    def apply_to_tiles(self, _tiles: list[Tile]) -> None:
        """Apply profile to all given tiles."""
        # TODO: Implement when profiles are available


# Property editor registry - maps property key to (label, editor_class)
PROPERTY_EDITORS: dict[str, tuple[str, type[PropertyEditor]]] = {
    "z_range": ("Z Range", ZRangeEditor),
    "profile": ("Profile", ProfileEditor),
}


# =============================================================================
# SelectionEditor - Unified editor using property editor widgets
# =============================================================================


class SelectionEditor(QWidget):
    """Unified editor for single or multiple tile selection.

    Single tile mode (R2, C3):
    - Shows position, status, profile details
    - Property editor (Z Range) with auto-save on change
    - Delete button for removing stack

    Multi-tile mode (5 selected):
    - Property dropdown to choose what to edit
    - Swappable property editor widget
    - Apply button to commit changes to all selected
    - Delete button for bulk removal
    """

    delete_requested = Signal(list)  # list of tiles to delete

    def __init__(self, grid_store: GridStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = grid_store
        self._tiles: list[Tile] = []
        self._updating = False

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = vbox(self, spacing=Spacing.SM)

        # Header: tile label (R2, C3) or count (5 selected) + status + delete button
        self._header_label = Text.section("R0, C0", color=Colors.TEXT)
        self._status_label = Text.muted("", size=10)

        self._delete_btn = ToolButton("mdi.trash-can-outline", color=Colors.ERROR, size=ControlSize.SM)
        self._delete_btn.setToolTip("Remove stack(s)")
        self._delete_btn.clicked.connect(self._on_delete_clicked)

        header = Flex.hstack(
            self._header_label,
            self._status_label,
            Stretch(),
            self._delete_btn,
            spacing=Spacing.XS,
        )
        layout.addWidget(header)

        # Single-tile details (hidden in multi-select mode)
        self._single_details = QWidget()
        single_layout = vbox(self._single_details, spacing=Spacing.XS)
        single_layout.setContentsMargins(0, 0, 0, 0)

        self._pos_label = Text.muted("Position: —")
        single_layout.addWidget(self._pos_label)

        self._profile_label = Text.muted("Profile: —")
        single_layout.addWidget(self._profile_label)

        layout.addWidget(self._single_details)

        # Multi-tile property selector (hidden in single-select mode)
        self._property_row = QWidget()
        prop_layout = vbox(self._property_row, spacing=Spacing.XS)
        prop_layout.setContentsMargins(0, 0, 0, 0)

        # Build options from registry
        property_options = [(key, label) for key, (label, _) in PROPERTY_EDITORS.items()]
        self._property_select = Select(options=property_options, value="z_range", size=ControlSize.SM)
        self._property_select.value_changed.connect(self._on_property_changed)

        prop_field = Flex.hstack(
            Text.muted("Edit:", size=11),
            self._property_select,
            Stretch(),
            spacing=Spacing.SM,
        )
        prop_layout.addWidget(prop_field)

        self._property_row.hide()
        layout.addWidget(self._property_row)

        # Property editors container
        self._editors_container = QWidget()
        editors_layout = vbox(self._editors_container, spacing=0)
        editors_layout.setContentsMargins(0, 0, 0, 0)

        # Create all property editors
        self._editors: dict[str, PropertyEditor] = {}
        for key, (_, editor_cls) in PROPERTY_EDITORS.items():
            editor = editor_cls(self._store)
            editor.value_changed.connect(self._on_editor_value_changed)
            editor.hide()
            editors_layout.addWidget(editor)
            self._editors[key] = editor

        # Show default editor
        self._current_editor_key = "z_range"
        self._editors[self._current_editor_key].show()

        layout.addWidget(self._editors_container)

        # Apply button (only for multi-select mode)
        self._apply_btn = ToolButton("mdi.check", color=Colors.SUCCESS, size=ControlSize.SM)
        self._apply_btn.setToolTip("Apply to all selected")
        self._apply_btn.clicked.connect(self._on_apply_clicked)

        self._apply_row = Flex.hstack(Stretch(), self._apply_btn, spacing=Spacing.SM)
        self._apply_row.hide()
        layout.addWidget(self._apply_row)

    def _connect_signals(self) -> None:
        self._store.selection_changed.connect(self._on_store_selection_changed)
        self._store.stacks_changed.connect(self._on_stacks_changed)

    def _current_editor(self) -> PropertyEditor:
        """Get the currently active property editor."""
        return self._editors[self._current_editor_key]

    def set_selection(self, tiles: list[Tile]) -> None:
        """Set the current selection."""
        self._tiles = tiles
        self._refresh_display()

    def _is_multi_select(self) -> bool:
        """Check if multiple tiles are selected."""
        return len(self._tiles) > 1

    def _on_store_selection_changed(self, _row: int, _col: int) -> None:
        """Handle store selection change (for single-select sync)."""
        if not self._is_multi_select():
            self._refresh_display()

    def _on_stacks_changed(self) -> None:
        """Handle stacks changed signal."""
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the display based on current selection."""
        self._updating = True

        if not self._tiles or len(self._tiles) == 1:
            self._show_single_tile_mode()
        else:
            self._show_multi_tile_mode()

        self._updating = False

    def _show_single_tile_mode(self) -> None:
        """Display single tile editing mode."""
        # Get tile from selection or store
        if self._tiles:
            tile = self._tiles[0]
            row, col = tile.row, tile.col
        else:
            row, col = self._store.selected_row, self._store.selected_col
            tile = self._store.get_selected_tile()

        stack = self._store.get_stack_at(row, col) if tile else None

        # Update header
        self._header_label.setText(f"R{row}, C{col}")

        # Update status and color
        if stack:
            status = stack.status.value if stack.status else ""
            color = get_stack_status_color(stack.status)
            self._header_label.setStyleSheet(f"color: {color};")
            self._status_label.setText(status)
            self._status_label.setStyleSheet(f"color: {color};")
            self._status_label.show()
        else:
            self._header_label.setStyleSheet(f"color: {Colors.TEXT};")
            self._status_label.setText("no stack")
            self._status_label.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            self._status_label.show()

        # Show single-tile details
        self._single_details.show()
        self._property_row.hide()
        self._apply_row.hide()

        # Update position
        if tile:
            self._pos_label.setText(f"Position: {tile.x_um / 1000:.2f}, {tile.y_um / 1000:.2f} mm")
        else:
            self._pos_label.setText("Position: —")

        # Update profile label
        if stack:
            self._profile_label.setText(f"Profile: {stack.profile_id}")
            self._delete_btn.show()
        else:
            self._profile_label.setText("Profile: —")
            self._delete_btn.hide()

        # Load values into Z Range editor (always shown in single mode)
        self._switch_editor("z_range")
        if tile:
            self._current_editor().load_from_tile(tile, stack)
        else:
            self._current_editor().load_defaults()

    def _show_multi_tile_mode(self) -> None:
        """Display multi-tile editing mode."""
        count = len(self._tiles)

        # Update header
        self._header_label.setText(f"{count} selected")
        self._header_label.setStyleSheet(f"color: {Colors.TEXT};")
        self._status_label.hide()

        # Hide single-tile details, show property selector
        self._single_details.hide()
        self._property_row.show()
        self._apply_row.show()
        self._delete_btn.show()

        # Load defaults into current editor
        self._current_editor().load_defaults()

    def _on_property_changed(self, prop: str) -> None:
        """Handle property dropdown change."""
        self._switch_editor(prop)
        self._current_editor().load_defaults()

    def _switch_editor(self, key: str) -> None:
        """Switch to a different property editor."""
        if key == self._current_editor_key:
            return

        # Hide current, show new
        self._editors[self._current_editor_key].hide()
        self._current_editor_key = key
        self._editors[key].show()

    def _on_editor_value_changed(self) -> None:
        """Handle value change from property editor."""
        if self._updating:
            return

        # Only auto-save in single-tile mode
        if not self._is_multi_select():
            self._save_single_tile()

    def _save_single_tile(self) -> None:
        """Save current editor values for single tile (auto-save)."""
        tile = self._tiles[0] if self._tiles else self._store.get_selected_tile()
        if tile:
            self._current_editor().apply_to_tiles([tile])

    def _on_apply_clicked(self) -> None:
        """Apply changes to all selected tiles (multi-select mode)."""
        if self._tiles:
            self._current_editor().apply_to_tiles(self._tiles)

    def _on_delete_clicked(self) -> None:
        """Handle delete button click."""
        if self._is_multi_select():
            # Emit signal for parent to handle (clears table selection too)
            self.delete_requested.emit(self._tiles)
        else:
            # Single tile delete
            if self._tiles:
                tile = self._tiles[0]
                row, col = tile.row, tile.col
            else:
                row, col = self._store.selected_row, self._store.selected_col
            self._store.remove_stacks([{"row": row, "col": col}])


class GridSettingsSection(QWidget):
    """Section for grid configuration settings."""

    def __init__(self, grid_store: GridStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = grid_store

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = vbox(self, spacing=Spacing.SM)

        # Header with lock indicator
        self._lock_icon = ToolButton(("mdi.lock", "mdi.lock-open-outline"), size=ControlSize.SM)
        self._lock_icon.setCheckable(True)
        self._lock_icon.setEnabled(False)  # Read-only indicator

        header = Flex.hstack(
            Text.section("Grid", color=Colors.TEXT),
            Stretch(),
            self._lock_icon,
            spacing=Spacing.XS,
        )
        layout.addWidget(header)

        # Grid settings form
        self._offset_x_spin = DoubleSpinBox(
            value=0.0, min_val=-10.0, max_val=10.0, decimals=2, step=0.1, size=ControlSize.SM
        )
        self._offset_x_spin.setSuffix(" mm")

        self._offset_y_spin = DoubleSpinBox(
            value=0.0, min_val=-10.0, max_val=10.0, decimals=2, step=0.1, size=ControlSize.SM
        )
        self._offset_y_spin.setSuffix(" mm")

        self._overlap_spin = DoubleSpinBox(
            value=0.1, min_val=0.0, max_val=0.5, decimals=2, step=0.05, size=ControlSize.SM
        )

        self._z_step_label = Text.muted("1.0 µm")

        self._order_select = Select(options=TILE_ORDER_OPTIONS, value="snake_row", size=ControlSize.SM)

        form = (
            GridFormBuilder(columns=2, spacing=Spacing.SM)
            .row(Field("Offset X", self._offset_x_spin), Field("Y", self._offset_y_spin))
            .row(Field("Overlap", self._overlap_spin), Field("Z Step", self._z_step_label))
            .row(Field("Order", self._order_select, span=2))
            .build()
        )
        layout.addWidget(form)

    def _connect_signals(self) -> None:
        self._store.grid_config_changed.connect(self._refresh_display)
        self._store.grid_locked_changed.connect(self._on_lock_changed)

        self._offset_x_spin.valueChanged.connect(self._on_offset_changed)
        self._offset_y_spin.valueChanged.connect(self._on_offset_changed)
        self._overlap_spin.valueChanged.connect(self._on_overlap_changed)
        self._order_select.value_changed.connect(self._on_order_changed)

    def _refresh_display(self) -> None:
        """Refresh display with current grid config."""
        config = self._store.grid_config

        # Block signals to prevent feedback loops
        self._offset_x_spin.blockSignals(True)
        self._offset_y_spin.blockSignals(True)
        self._overlap_spin.blockSignals(True)
        self._order_select.blockSignals(True)

        self._offset_x_spin.setValue(config.x_offset_um / 1000)
        self._offset_y_spin.setValue(config.y_offset_um / 1000)
        self._overlap_spin.setValue(config.overlap)
        self._z_step_label.setText(f"{config.z_step_um:.1f} µm")
        self._order_select.set_value(self._store.tile_order)

        self._offset_x_spin.blockSignals(False)
        self._offset_y_spin.blockSignals(False)
        self._overlap_spin.blockSignals(False)
        self._order_select.blockSignals(False)

        self._update_locked_state()

    def _on_lock_changed(self, locked: bool) -> None:
        """Handle grid lock state change."""
        self._lock_icon.setChecked(locked)
        self._update_locked_state()

    def _update_locked_state(self) -> None:
        """Update widget enabled state based on lock."""
        locked = self._store.grid_locked
        self._lock_icon.setChecked(locked)
        self._offset_x_spin.setEnabled(not locked)
        self._offset_y_spin.setEnabled(not locked)
        self._overlap_spin.setEnabled(not locked)
        # Order can always be changed

    def _on_offset_changed(self) -> None:
        """Handle offset change."""
        if self._store.grid_locked:
            return
        x_um = self._offset_x_spin.value() * 1000
        y_um = self._offset_y_spin.value() * 1000
        fire_and_forget(self._store.set_grid_offset(x_um, y_um), log=log)

    def _on_overlap_changed(self) -> None:
        """Handle overlap change."""
        if self._store.grid_locked:
            return
        fire_and_forget(self._store.set_overlap(self._overlap_spin.value()), log=log)

    def _on_order_changed(self, order: TileOrder) -> None:
        """Handle tile order change."""
        self._store.set_tile_order(order)


# =============================================================================
# Stage Canvas Sub-widgets
# =============================================================================

# Colors used for stage visualization
_EMERALD = "#10b981"
_ROSE = "#f43f5e"
_FUCHSIA = "#d946ef"
_AMBER = "#f59e0b"
_ZINC_600 = "#52525b"
_ZINC_700 = "#3f3f46"
_ZINC_900 = "#18181b"

# Layer toggle button colors (matching web)
_LAYER_COLORS: dict[str, str] = {
    "grid": "#60a5fa",  # blue-400
    "stacks": "#c084fc",  # purple-400
    "path": "#e879f9",  # fuchsia-400
    "fov": "#34d399",  # emerald-400
    "thumbnail": "#22d3ee",  # cyan-400
}

_TRACK_WIDTH = 16
_STAGE_GAP = 16


class _StageSlider(QWidget):
    """Thin custom slider for stage axis control."""

    valueChanged = Signal(float)

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._orientation = orientation
        self._min = 0.0
        self._max = 100.0
        self._value = 0.0
        self._moving = False
        self._dragging = False
        self._inverted = False

        if orientation == Qt.Orientation.Horizontal:
            self.setFixedHeight(_TRACK_WIDTH)
            self.setMinimumWidth(20)
        else:
            self.setFixedWidth(_TRACK_WIDTH)
            self.setMinimumHeight(20)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setRange(self, min_val: float, max_val: float) -> None:
        self._min = min_val
        self._max = max_val
        self.update()

    def setValue(self, value: float) -> None:
        self._value = value
        self.update()

    def setMoving(self, moving: bool) -> None:
        self._moving = moving
        self.update()

    def setInverted(self, inverted: bool) -> None:
        self._inverted = inverted

    def _value_to_ratio(self) -> float:
        r = self._max - self._min
        if r <= 0:
            return 0.0
        ratio = (self._value - self._min) / r
        if self._inverted:
            ratio = 1.0 - ratio
        return max(0.0, min(1.0, ratio))

    def _ratio_to_value(self, ratio: float) -> float:
        if self._inverted:
            ratio = 1.0 - ratio
        return self._min + ratio * (self._max - self._min)

    def paintEvent(self, _event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        painter.setPen(QPen(QColor(_ZINC_600), 0.5))
        painter.setBrush(QColor(_ZINC_900))
        painter.drawRect(QRectF(0, 0, w, h))

        # Thumb line
        color = QColor(_ROSE) if self._moving else QColor(_EMERALD)
        ratio = self._value_to_ratio()

        pen = QPen(color, 2)
        painter.setPen(pen)
        if self._orientation == Qt.Orientation.Horizontal:
            x = ratio * w
            painter.drawLine(QPointF(x, 0), QPointF(x, h))
        else:
            y = (1.0 - ratio) * h  # vertical: top = max
            painter.drawLine(QPointF(0, y), QPointF(w, y))

        painter.end()

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event and not self._moving and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._handle_mouse(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event and self._dragging:
            self._handle_mouse(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event and self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def _handle_mouse(self, event: QMouseEvent) -> None:
        if self._orientation == Qt.Orientation.Horizontal:
            ratio = max(0.0, min(1.0, event.position().x() / max(1, self.width())))
        else:
            ratio = max(0.0, min(1.0, 1.0 - event.position().y() / max(1, self.height())))
        value = self._ratio_to_value(ratio)
        self._value = value
        self.update()
        self.valueChanged.emit(value)


class _StageCanvas(QWidget):
    """Core QPainter widget for 2D stage visualization.

    Draws tile grid, stacks, acquisition path, FOV indicator, and thumbnail.
    All coordinates are in mm (tile µm / 1000).
    """

    tile_clicked = Signal(int, int)  # row, col
    tile_double_clicked = Signal(int, int)  # row, col

    def __init__(
        self,
        grid_store: GridStore,
        stage_store: StageStore,
        preview_store: PreviewStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._grid = grid_store
        self._stage = stage_store
        self._preview = preview_store

        self._show_thumbnail = True
        self._hovered_tile: tuple[int, int] | None = None
        self._thumbnail_image: QImage | None = None

        # Cache transform
        self._transform = QTransform()
        self._inv_transform = QTransform()

        self.setMouseTracking(True)
        self.setMinimumSize(100, 100)

        # Connect signals
        self._grid.tiles_changed.connect(self.update)
        self._grid.stacks_changed.connect(self.update)
        self._grid.grid_config_changed.connect(self.update)
        self._grid.selection_changed.connect(self._on_selection_changed)
        self._grid.layer_visibility_changed.connect(self.update)

        self._stage.position_changed.connect(self.update)
        self._stage.moving_changed.connect(self._on_moving_changed)
        self._stage.limits_changed.connect(self.update)

        self._preview.composite_updated.connect(self._on_composite_updated)

    def set_show_thumbnail(self, show: bool) -> None:
        self._show_thumbnail = show
        self.update()

    def _on_selection_changed(self, _row: int, _col: int) -> None:
        self.update()

    def _on_moving_changed(self) -> None:
        if self._stage.is_xy_moving:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def _on_composite_updated(self) -> None:
        channels = self._preview.channels
        if not channels:
            self._thumbnail_image = None
            self.update()
            return

        frames = [ch.frame for ch in channels.values()]
        composite = composite_rgb(frames)
        if composite is None:
            self._thumbnail_image = None
        else:
            resized = resize_image(composite, 256)
            h, w = resized.shape[:2]
            # .copy() to detach from numpy buffer
            data = resized.copy().data
            self._thumbnail_image = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        self.update()

    def _to_mm(self, um: float) -> float:
        return um / 1000.0

    def _compute_transform(self) -> None:
        """Compute world-to-widget transform maintaining aspect ratio."""
        fov_w, fov_h = self._grid.fov_size
        fov_w_mm = self._to_mm(fov_w)
        fov_h_mm = self._to_mm(fov_h)

        margin_x = fov_w_mm / 2.0
        margin_y = fov_h_mm / 2.0

        stage_w = self._stage.stage_width
        stage_h = self._stage.stage_height

        if stage_w <= 0 or stage_h <= 0:
            stage_w = fov_w_mm * 2
            stage_h = fov_h_mm * 2

        vb_w = stage_w + fov_w_mm
        vb_h = stage_h + fov_h_mm

        if vb_w <= 0 or vb_h <= 0:
            return

        w = self.width()
        h = self.height()

        scale_x = w / vb_w
        scale_y = h / vb_h
        scale = min(scale_x, scale_y)

        # Center the content
        used_w = vb_w * scale
        used_h = vb_h * scale
        offset_x = (w - used_w) / 2.0
        offset_y = (h - used_h) / 2.0

        self._transform = QTransform()
        self._transform.translate(offset_x, offset_y)
        self._transform.scale(scale, scale)
        self._transform.translate(margin_x, margin_y)

        inv, invertible = self._transform.inverted()
        self._inv_transform = inv if invertible else QTransform()

    def paintEvent(self, _event: QPaintEvent | None) -> None:
        self._compute_transform()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dark background
        painter.fillRect(self.rect(), QColor(str(Colors.BG_DARK)))

        painter.setTransform(self._transform)

        vis = self._grid.layer_visibility
        tiles = self._grid.tiles
        stacks = self._grid.stacks

        # 1. Stacks layer
        if vis.stacks and stacks:
            self._paint_stacks(painter, stacks)

        # 2. Path layer
        if vis.path and len(stacks) > 1:
            self._paint_path(painter, stacks)

        # 3. FOV layer
        if vis.fov:
            self._paint_fov(painter)

        # 4. Grid layer (tiles on top for click targeting)
        if vis.grid and tiles:
            self._paint_grid(painter, tiles)

        painter.end()

    def _paint_stacks(self, painter: QPainter, stacks: list[Stack]) -> None:
        for stack in stacks:
            cx = self._to_mm(stack.x_um)
            cy = self._to_mm(stack.y_um)
            w = self._to_mm(stack.w_um)
            h = self._to_mm(stack.h_um)
            x = cx - w / 2
            y = cy - h / 2
            rect = QRectF(x, y, w, h)

            color_hex = get_stack_status_color(stack.status)
            color = QColor(color_hex)

            # Check hover
            is_hovered = self._hovered_tile == (stack.row, stack.col)

            # Fill with alpha
            fill_color = QColor(color)
            fill_color.setAlphaF(0.35 if is_hovered else 0.15)
            painter.setBrush(fill_color)

            # Stroke
            pen = QPen(color)
            pen.setCosmetic(True)
            pen.setWidthF(1.5)
            painter.setPen(pen)

            painter.drawRect(rect)

    def _paint_path(self, painter: QPainter, stacks: list[Stack]) -> None:
        points = [QPointF(self._to_mm(s.x_um), self._to_mm(s.y_um)) for s in stacks]

        # Polyline
        pen = QPen(QColor(_FUCHSIA))
        pen.setCosmetic(True)
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(points))

        # Arrowheads at midpoints
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())

            # Arrow size in world coords - scale to be visible
            arrow_size = 0.15
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)

            # Arrow points (relative to mid, rotated by angle)
            # M -0.15 -0.2  L 0.15 0  L -0.15 0.2
            ax1 = mid.x() + (-arrow_size * cos_a - (-0.2) * sin_a)
            ay1 = mid.y() + (-arrow_size * sin_a + (-0.2) * cos_a)
            ax2 = mid.x() + (arrow_size * cos_a)
            ay2 = mid.y() + (arrow_size * sin_a)
            ax3 = mid.x() + (-arrow_size * cos_a - 0.2 * sin_a)
            ay3 = mid.y() + (-arrow_size * sin_a + 0.2 * cos_a)

            path = QPainterPath()
            path.moveTo(ax1, ay1)
            path.lineTo(ax2, ay2)
            path.lineTo(ax3, ay3)

            pen = QPen(QColor(_FUCHSIA))
            pen.setCosmetic(True)
            pen.setWidthF(1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

    def _paint_fov(self, painter: QPainter) -> None:
        fov_w_mm = self._to_mm(self._grid.fov_size[0])
        fov_h_mm = self._to_mm(self._grid.fov_size[1])

        # FOV position relative to stage lower limits
        fov_x = self._stage.x.position - self._stage.x.lower_limit
        fov_y = self._stage.y.position - self._stage.y.lower_limit

        left = fov_x - fov_w_mm / 2
        top = fov_y - fov_h_mm / 2
        fov_rect = QRectF(left, top, fov_w_mm, fov_h_mm)

        is_moving = self._stage.is_xy_moving
        color = QColor(_ROSE) if is_moving else QColor(_EMERALD)

        # Thumbnail
        if self._show_thumbnail and self._thumbnail_image is not None:
            painter.save()
            painter.setClipRect(fov_rect)
            painter.drawImage(fov_rect, self._thumbnail_image)
            painter.restore()

        # FOV outline
        pen = QPen(color)
        pen.setCosmetic(True)
        pen.setWidthF(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(fov_rect)

        # Crosshair
        crosshair_len = 0.3
        pen_ch = QPen(color)
        pen_ch.setCosmetic(True)
        pen_ch.setWidthF(1)
        color_ch = QColor(color)
        color_ch.setAlphaF(0.7)
        pen_ch.setColor(color_ch)
        painter.setPen(pen_ch)
        painter.drawLine(QPointF(fov_x - crosshair_len, fov_y), QPointF(fov_x + crosshair_len, fov_y))
        painter.drawLine(QPointF(fov_x, fov_y - crosshair_len), QPointF(fov_x, fov_y + crosshair_len))

    def _paint_grid(self, painter: QPainter, tiles: list[Tile]) -> None:
        sel_row = self._grid.selected_row
        sel_col = self._grid.selected_col
        selected_tile: Tile | None = None

        for tile in tiles:
            if tile.row == sel_row and tile.col == sel_col:
                selected_tile = tile
                continue  # draw selected last
            self._paint_tile(painter, tile, selected=False)

        # Draw selected tile on top
        if selected_tile is not None:
            self._paint_tile(painter, selected_tile, selected=True)

    def _paint_tile(self, painter: QPainter, tile: Tile, *, selected: bool) -> None:
        cx = self._to_mm(tile.x_um)
        cy = self._to_mm(tile.y_um)
        w = self._to_mm(tile.w_um)
        h = self._to_mm(tile.h_um)
        x = cx - w / 2
        y = cy - h / 2
        rect = QRectF(x, y, w, h)

        is_hovered = self._hovered_tile == (tile.row, tile.col)

        if is_hovered:
            fill = QColor(_ZINC_700)
            fill.setAlphaF(0.3)
            painter.setBrush(fill)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        if selected:
            pen = QPen(QColor(_AMBER))
            pen.setCosmetic(True)
            pen.setWidthF(2)
        else:
            pen = QPen(QColor(_ZINC_700))
            pen.setCosmetic(True)
            pen.setWidthF(1)
        painter.setPen(pen)
        painter.drawRect(rect)

    def _hit_test(self, pos: QPointF) -> tuple[int, int] | None:
        """Hit test against tiles, return (row, col) or None."""
        world = self._inv_transform.map(pos)
        wx, wy = world.x(), world.y()

        for tile in self._grid.tiles:
            cx = self._to_mm(tile.x_um)
            cy = self._to_mm(tile.y_um)
            w = self._to_mm(tile.w_um)
            h = self._to_mm(tile.h_um)
            if cx - w / 2 <= wx <= cx + w / 2 and cy - h / 2 <= wy <= cy + h / 2:
                return (tile.row, tile.col)
        return None

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test(event.position())
            if hit:
                self._grid.select_tile(hit[0], hit[1])
                self.tile_clicked.emit(hit[0], hit[1])

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test(event.position())
            if hit:
                self.tile_double_clicked.emit(hit[0], hit[1])

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event:
            hit = self._hit_test(event.position())
            if hit != self._hovered_tile:
                self._hovered_tile = hit
                self.update()


class _ZVisualization(QWidget):
    """Transparent overlay drawn on top of Z slider showing z-position and stack range."""

    def __init__(self, stage_store: StageStore, grid_store: GridStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stage = stage_store
        self._grid = grid_store
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._stage.position_changed.connect(self.update)
        self._stage.moving_changed.connect(self.update)
        self._grid.selection_changed.connect(self._on_selection)
        self._grid.stacks_changed.connect(self.update)

    def _on_selection(self, _r: int, _c: int) -> None:
        self.update()

    def _z_to_y(self, z_value: float) -> float:
        depth = self._stage.stage_depth
        if depth <= 0:
            return 0.0
        offset = z_value - self._stage.z.lower_limit
        return (1.0 - offset / depth) * self.height()

    def paintEvent(self, _event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()

        # Selected stack z markers
        selected_stack = self._grid.get_selected_stack()
        if selected_stack and self._stage.stage_depth > 0:
            color = QColor(get_stack_status_color(selected_stack.status))
            pen = QPen(color)
            pen.setCosmetic(True)
            pen.setWidthF(2)
            painter.setPen(pen)

            z0_mm = selected_stack.z_start_um / 1000.0
            z1_mm = selected_stack.z_end_um / 1000.0
            y0 = self._z_to_y(z0_mm)
            y1 = self._z_to_y(z1_mm)
            painter.drawLine(QPointF(0, y0), QPointF(w, y0))
            painter.drawLine(QPointF(0, y1), QPointF(w, y1))

        # Z position line
        is_moving = self._stage.is_z_moving
        color = QColor(_ROSE) if is_moving else QColor(_EMERALD)
        pen = QPen(color)
        pen.setCosmetic(True)
        pen.setWidthF(2)
        painter.setPen(pen)

        y = self._z_to_y(self._stage.z.position)
        painter.drawLine(QPointF(0, y), QPointF(w, y))

        painter.end()


class _LayerToggleBar(QWidget):
    """Floating toolbar with layer toggle buttons."""

    def __init__(self, grid_store: GridStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = grid_store
        self._show_thumbnail = True

        self.setStyleSheet("background-color: rgba(24, 24, 27, 204); border-radius: 4px;")

        layout = vbox(self, spacing=0, margins=(2, 2, 2, 2))

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(1)

        self._btns: dict[str, ToolButton] = {}
        icons = {
            "grid": "mdi.grid",
            "stacks": "mdi.layers",
            "path": "mdi.vector-polyline",
            "fov": "mdi.crosshairs",
            "thumbnail": "mdi.image",
        }

        for key, icon_name in icons.items():
            color = _LAYER_COLORS[key]
            btn = ToolButton(
                icon_name,
                checkable=True,
                size=ControlSize.SM,
                color=color,
                color_hover=color,
            )
            btn.setChecked(True)
            btn.setToolTip(f"Toggle {key}")
            btn.toggled.connect(lambda checked, k=key: self._on_toggled(k, checked))
            row.addWidget(btn)
            self._btns[key] = btn

        layout.addLayout(row)

        # Sync initial state
        self._grid.layer_visibility_changed.connect(self._sync_state)

    @property
    def show_thumbnail(self) -> bool:
        return self._show_thumbnail

    def _on_toggled(self, key: str, checked: bool) -> None:
        if key == "thumbnail":
            self._show_thumbnail = checked
            parent = self.parent()
            if isinstance(parent, GridCanvas):
                parent.set_show_thumbnail(checked)
        else:
            self._grid.set_layer_visibility(key, checked)

    def _sync_state(self) -> None:
        vis = self._grid.layer_visibility
        for key in ("grid", "stacks", "path", "fov"):
            btn = self._btns[key]
            btn.blockSignals(True)
            btn.setChecked(getattr(vis, key))
            btn.blockSignals(False)


class GridCanvas(QWidget):
    """2D stage visualization with grid, tiles, stacks, FOV, sliders, and layer toggles.

    Composite widget assembling _StageCanvas, _StageSliders, _ZVisualization,
    and _LayerToggleBar into a complete stage visualization panel.
    """

    def __init__(
        self,
        preview_store: PreviewStore,
        grid_store: GridStore,
        stage_store: StageStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._preview = preview_store
        self._grid = grid_store
        self._stage = stage_store

        self.setStyleSheet(f"background-color: {Colors.BG_DARK};")

        # Sub-widgets
        self._canvas = _StageCanvas(grid_store, stage_store, preview_store, self)

        self._x_slider = _StageSlider(Qt.Orientation.Horizontal, self)
        self._y_slider = _StageSlider(Qt.Orientation.Vertical, self)
        self._z_slider = _StageSlider(Qt.Orientation.Vertical, self)
        self._z_slider.setInverted(True)

        self._z_viz = _ZVisualization(stage_store, grid_store, self)
        self._toggle_bar = _LayerToggleBar(grid_store, self)

        # Layout: grid with sliders on edges
        layout = QGridLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        #  row 0: [empty] [x_slider] [empty]
        #  row 1: [y_slider] [canvas] [z_area]
        layout.addWidget(self._x_slider, 0, 1)
        layout.addWidget(self._y_slider, 1, 0)
        layout.addWidget(self._canvas, 1, 1)

        # Z area: stack z_slider and z_viz overlaid
        z_container = QWidget(self)
        z_container.setFixedWidth(_TRACK_WIDTH + 4)
        z_layout = QGridLayout(z_container)
        z_layout.setContentsMargins(2, 0, 0, 0)
        z_layout.setSpacing(0)
        z_layout.addWidget(self._z_slider, 0, 0)
        z_layout.addWidget(self._z_viz, 0, 0)  # overlaid on z_slider
        layout.addWidget(z_container, 1, 2)

        layout.setColumnStretch(1, 1)
        layout.setRowStretch(1, 1)

        # Connect slider -> stage move
        self._x_slider.valueChanged.connect(self._on_x_slider)
        self._y_slider.valueChanged.connect(self._on_y_slider)
        self._z_slider.valueChanged.connect(self._on_z_slider)

        # Connect stage -> slider updates
        self._stage.position_changed.connect(self._sync_sliders)
        self._stage.moving_changed.connect(self._sync_slider_moving)
        self._stage.limits_changed.connect(self._sync_slider_ranges)

        # Canvas double-click -> move stage
        self._canvas.tile_double_clicked.connect(self._on_tile_double_clicked)

    def set_show_thumbnail(self, show: bool) -> None:
        """Set thumbnail visibility on the stage canvas."""
        self._canvas.set_show_thumbnail(show)

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        # Position toggle bar in top-right corner
        bar_w = self._toggle_bar.sizeHint().width()
        self._toggle_bar.move(self.width() - bar_w - 8, 4)
        self._toggle_bar.raise_()

    def _sync_sliders(self) -> None:
        self._x_slider.blockSignals(True)
        self._y_slider.blockSignals(True)
        self._z_slider.blockSignals(True)

        self._x_slider.setValue(self._stage.x.position)
        self._y_slider.setValue(self._stage.y.position)
        self._z_slider.setValue(self._stage.z.position)

        self._x_slider.blockSignals(False)
        self._y_slider.blockSignals(False)
        self._z_slider.blockSignals(False)

    def _sync_slider_moving(self) -> None:
        self._x_slider.setMoving(self._stage.is_xy_moving)
        self._y_slider.setMoving(self._stage.is_xy_moving)
        self._z_slider.setMoving(self._stage.is_z_moving)

    def _sync_slider_ranges(self) -> None:
        self._x_slider.setRange(self._stage.x.lower_limit, self._stage.x.upper_limit)
        self._y_slider.setRange(self._stage.y.lower_limit, self._stage.y.upper_limit)
        self._z_slider.setRange(self._stage.z.lower_limit, self._stage.z.upper_limit)

    def _on_x_slider(self, value: float) -> None:
        if self._stage.x_adapter and not self._stage.is_xy_moving:
            fire_and_forget(self._stage.x_adapter.call("move_abs", value), log=log)

    def _on_y_slider(self, value: float) -> None:
        if self._stage.y_adapter and not self._stage.is_xy_moving:
            fire_and_forget(self._stage.y_adapter.call("move_abs", value), log=log)

    def _on_z_slider(self, value: float) -> None:
        if self._stage.z_adapter and not self._stage.is_z_moving:
            fire_and_forget(self._stage.z_adapter.call("move_abs", value), log=log)

    def _on_tile_double_clicked(self, row: int, col: int) -> None:
        """Move stage to tile center on double-click."""
        if self._stage.is_xy_moving:
            return
        for tile in self._grid.tiles:
            if tile.row == row and tile.col == col:
                target_x = self._stage.x.lower_limit + tile.x_um / 1000.0
                target_y = self._stage.y.lower_limit + tile.y_um / 1000.0
                # Clamp to limits
                target_x = max(self._stage.x.lower_limit, min(self._stage.x.upper_limit, target_x))
                target_y = max(self._stage.y.lower_limit, min(self._stage.y.upper_limit, target_y))
                if self._stage.x_adapter:
                    fire_and_forget(self._stage.x_adapter.call("move_abs", target_x), log=log)
                if self._stage.y_adapter:
                    fire_and_forget(self._stage.y_adapter.call("move_abs", target_y), log=log)
                break


class GridPanel(QWidget):
    """Grid panel with table on the left and tile/stack editing on the right.

    Layout:
    - Left: GridTable (expandable)
    - Right: Filter + SelectionEditor at top, GridSettingsSection at bottom
    """

    # Emitted when a tile is double-clicked (for stage movement)
    tile_double_clicked = Signal(int, int)  # row, col

    def __init__(self, grid_store: GridStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = grid_store
        self.setStyleSheet(f"background-color: {Colors.BG_DARK};")

        # Left: Grid table
        self._grid_table = GridTable(self._store)
        self._grid_table.row_double_clicked.connect(self.tile_double_clicked.emit)
        self._grid_table.selection_changed.connect(self._on_selection_changed)

        # Right panel sections
        self._selection_editor = SelectionEditor(self._store)
        self._selection_editor.delete_requested.connect(self._on_delete_requested)
        self._grid_section = GridSettingsSection(self._store)

        # Filter dropdown
        self._filter_select = Select(options=GRID_FILTER_OPTIONS, value="all", size=ControlSize.SM)
        self._filter_select.value_changed.connect(self._on_filter_changed)

        top_row = Flex.hstack(
            self._filter_select,
            Stretch(),
            spacing=Spacing.SM,
        )

        right_panel = Flex.vstack(
            top_row,
            Separator(),
            self._selection_editor,
            Stretch(),
            Separator(),
            self._grid_section,
            spacing=Spacing.SM,
            padding=(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD),
            background=Colors.BG_DARK,
        )
        right_panel.setFixedWidth(320)

        # Main layout: table | separator | right panel
        main = Flex.hstack(
            (self._grid_table, 1),  # stretch=1
            Separator(orientation="vertical"),
            right_panel,
            spacing=0,
        )

        layout = vbox(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(main)

    def _on_filter_changed(self, mode: str) -> None:
        """Handle filter change."""
        self._grid_table.set_filter(mode)

    def _on_selection_changed(self, count: int) -> None:
        """Handle table selection change - update editor."""
        selected_tiles = self._grid_table.get_selected_tiles() if count > 0 else []
        self._selection_editor.set_selection(selected_tiles)

    def _on_delete_requested(self, tiles: list[Tile]) -> None:
        """Handle delete request from editor."""
        positions = [{"row": t.row, "col": t.col} for t in tiles]
        if positions:
            self._store.remove_stacks(positions)
            self._grid_table.clear_selection()
