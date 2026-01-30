"""Grid panel for acquisition grid display and control."""

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget

from vxl.config import TileOrder
from vxl.tile import Box as TileBox
from vxl.tile import Tile
from vxl_qt.store import STACK_STATUS_COLORS, GridStore, PreviewStore, get_stack_status_color
from vxl_qt.ui.kit import (
    Box,
    Colors,
    ColumnType,
    ControlSize,
    DoubleSpinBox,
    Field,
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
from vxl_qt.ui.panels.preview import PreviewThumbnail
from vxlib import fire_and_forget

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


class GridTableModel(TableModel[Tile, TileBox | None]):
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

    def _get_aux_data(self, row_data: Tile) -> TileBox | None:
        """Get stack for a tile."""
        return self._store.get_stack_at(row_data.row, row_data.col)

    def _on_edit(self, row_data: Tile, aux_data: TileBox | None, column: TableColumn, value: Any) -> None:
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

    def load_from_tile(self, _tile: Tile, _stack: TileBox | None) -> None:
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

    def load_from_tile(self, _tile: Tile, _stack: TileBox | None) -> None:
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

    def load_from_tile(self, _tile: Tile, _stack: TileBox | None) -> None:
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

        header = Box.hstack(
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

        prop_field = Box.hstack(
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

        self._apply_row = Box.hstack(Stretch(), self._apply_btn, spacing=Spacing.SM)
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

        header = Box.hstack(
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


class GridCanvas(QWidget):
    """2D stage visualization with grid, tiles, stacks, and FOV.

    TODO: Implement using QSvgRenderer + QPainter pattern (like WheelGraphic):
    - Grid layer: Tile rectangles (clickable for selection)
    - Stacks layer: Box rectangles with status-based coloring
    - Path layer: Acquisition order polyline with arrows
    - FOV layer: Current position with thumbnail and crosshair
    - X/Y sliders for stage movement
    - Z slider (vertical) for depth control
    - Layer visibility toggle buttons
    """

    def __init__(
        self,
        preview_store: PreviewStore,
        grid_store: GridStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._preview_store = preview_store
        self._grid_store = grid_store

        self.setStyleSheet(f"background-color: {Colors.BG_DARK};")

        layout = vbox(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Placeholder for now
        label = Text.muted("Grid Canvas (Coming Soon)", color=Colors.TEXT_DISABLED)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        # Preview thumbnail for FOV reference
        self._thumbnail = PreviewThumbnail(self._preview_store, target_width=200)
        layout.addWidget(self._thumbnail, alignment=Qt.AlignmentFlag.AlignHCenter)


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

        top_row = Box.hstack(
            self._filter_select,
            Stretch(),
            spacing=Spacing.SM,
        )

        right_panel = Box.vstack(
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
        main = Box.hstack(
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
