"""Reusable table components for the Voxel Qt application.

Provides a flexible table system with:
- Column definitions with type-specific rendering and editing
- Generic model base class for data binding
- Custom delegates for checkboxes, spinboxes, and status colors
- Styled table widget with dark theme
- Toolbar with filter dropdowns and bulk actions
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from .button import ToolButton
from .input import DoubleSpinBox, Select, SpinBox
from .layout import vbox
from .stack import Box, Stretch
from .text import FontSize, Text
from .theme import Colors, ControlSize, Spacing


class ColumnType(Enum):
    """Column data types that determine rendering and editing behavior."""

    TEXT = auto()  # Plain text (read-only)
    CHECKBOX = auto()  # Checkbox for bulk selection
    SPINBOX = auto()  # Integer spinbox (editable)
    DOUBLE_SPINBOX = auto()  # Float spinbox (editable)
    STATUS = auto()  # Colored status text


@dataclass
class TableColumn:
    """Definition for a table column.

    Usage:
        # Simple text column
        TableColumn(
            key="tile",
            header="Tile",
            width=80,
            getter=lambda tile, stack: f"R{tile.row}, C{tile.col}",
        )

        # Editable spinbox column
        TableColumn(
            key="z_start",
            header="Z Start",
            column_type=ColumnType.SPINBOX,
            width=90,
            getter=lambda tile, stack: int(stack.z_start_um) if stack else 0,
            setter=lambda tile, stack, value: {"z_start_um": value},
            editable=lambda tile, stack: stack is not None,
            suffix=" um",
            min_val=-100000,
            max_val=100000,
            step=10,
        )

        # Status column with colors
        TableColumn(
            key="status",
            header="Status",
            column_type=ColumnType.STATUS,
            getter=lambda tile, stack: stack.status.value if stack else "",
            status_colors={"planned": "#3a6ea5", "completed": "#4ec9b0"},
        )
    """

    key: str  # Unique identifier
    header: str  # Column header text
    column_type: ColumnType = ColumnType.TEXT  # Determines delegate behavior
    width: int | None = None  # Fixed width (None = stretch)
    min_width: int = 40  # Minimum width

    # Data binding
    getter: Callable[[Any, Any], Any] | None = None  # (row_data, aux_data) -> display_value
    setter: Callable[[Any, Any, Any], dict] | None = None  # (row_data, aux_data, new_value) -> edit_dict
    editable: Callable[[Any, Any], bool] | None = None  # (row_data, aux_data) -> bool

    # Spinbox options
    suffix: str = ""
    min_val: float = 0
    max_val: float = 100000
    step: float = 1
    decimals: int = 0  # For DOUBLE_SPINBOX

    # Status column colors
    status_colors: dict[str, str] = field(default_factory=dict)

    # Alignment
    align: str = "left"  # "left", "center", "right"

    def get_alignment(self) -> Qt.AlignmentFlag:
        """Get Qt alignment flag from string."""
        if self.align == "center":
            return Qt.AlignmentFlag.AlignCenter
        if self.align == "right":
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


class TableModel[T, A](QAbstractTableModel):
    """Generic table model for the kit's Table component.

    Subclass this to create domain-specific models by implementing:
    - _get_rows(): Return list of row data
    - _get_aux_data(row): Return auxiliary data for a row
    - _on_edit(row, aux, column, value): Handle edit commits

    Usage:
        class GridTableModel(TableModel[Tile, Box | None]):
            def __init__(self, store: GridStore, columns: list[TableColumn]):
                super().__init__(columns)
                self._store = store
                self._store.tiles_changed.connect(self.refresh)

            def _get_rows(self) -> list[Tile]:
                return self._store.tiles

            def _get_aux_data(self, tile: Tile) -> Box | None:
                return self._store.get_stack_at(tile.row, tile.col)
    """

    # Signal emitted when checkbox selection changes
    checked_changed = Signal()

    def __init__(self, columns: list[TableColumn], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._columns = columns
        self._checked: set[int] = set()  # Row indices of checked items
        self._rows_cache: list[T] | None = None  # Cache for _get_rows()

    # --- Abstract methods to override ---

    def _get_rows(self) -> list[T]:
        """Return the list of row data items. Override in subclass."""
        raise NotImplementedError

    def _get_aux_data(self, row_data: T) -> A:
        """Return auxiliary data for a row (e.g., stack for a tile). Override in subclass."""
        raise NotImplementedError

    def _on_edit(self, row_data: T, aux_data: A, column: TableColumn, value: Any) -> None:
        """Handle edit commit. Override to persist changes."""

    # --- Cached row access ---

    def _rows(self) -> list[T]:
        """Get rows with caching."""
        if self._rows_cache is None:
            self._rows_cache = self._get_rows()
        return self._rows_cache

    def _invalidate_cache(self) -> None:
        """Invalidate the rows cache."""
        self._rows_cache = None

    # --- QAbstractTableModel implementation ---

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows())

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._columns)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None

        rows = self._rows()
        if index.row() >= len(rows):
            return None

        row_data = rows[index.row()]
        aux_data = self._get_aux_data(row_data)
        column = self._columns[index.column()]

        # Checkbox column
        if column.column_type == ColumnType.CHECKBOX:
            if role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if index.row() in self._checked else Qt.CheckState.Unchecked
            return None

        # Get value from getter
        value = column.getter(row_data, aux_data) if column.getter else ""

        if role == Qt.ItemDataRole.DisplayRole:
            if column.column_type in (ColumnType.SPINBOX, ColumnType.DOUBLE_SPINBOX):
                # Format with suffix for display
                if column.column_type == ColumnType.DOUBLE_SPINBOX:
                    return f"{value:.{column.decimals}f}{column.suffix}"
                return f"{value}{column.suffix}"
            return str(value) if value is not None else ""

        if role == Qt.ItemDataRole.EditRole:
            return value

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return column.get_alignment()

        if role == Qt.ItemDataRole.ForegroundRole:
            if column.column_type == ColumnType.STATUS and column.status_colors:
                color = column.status_colors.get(str(value), Colors.TEXT_MUTED)
                return QColor(color)
            return QColor(Colors.TEXT)

        return None

    def setData(
        self, index: QModelIndex | QPersistentModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if not index.isValid():
            return False

        column = self._columns[index.column()]

        # Handle checkbox
        if column.column_type == ColumnType.CHECKBOX and role == Qt.ItemDataRole.CheckStateRole:
            if value == Qt.CheckState.Checked:
                self._checked.add(index.row())
            else:
                self._checked.discard(index.row())
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            self.checked_changed.emit()
            return True

        # Handle edits
        if role == Qt.ItemDataRole.EditRole:
            rows = self._rows()
            if index.row() >= len(rows):
                return False

            row_data = rows[index.row()]
            aux_data = self._get_aux_data(row_data)
            self._on_edit(row_data, aux_data, column, value)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
            return True

        return False

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        base_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        column = self._columns[index.column()]

        if column.column_type == ColumnType.CHECKBOX:
            return base_flags | Qt.ItemFlag.ItemIsUserCheckable

        if column.column_type in (ColumnType.SPINBOX, ColumnType.DOUBLE_SPINBOX):
            # Check if editable
            if column.editable:
                rows = self._rows()
                if index.row() < len(rows):
                    row_data = rows[index.row()]
                    aux_data = self._get_aux_data(row_data)
                    if column.editable(row_data, aux_data):
                        return base_flags | Qt.ItemFlag.ItemIsEditable
            elif column.setter:
                # If no editable function but has setter, assume editable
                return base_flags | Qt.ItemFlag.ItemIsEditable

        return base_flags

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self._columns):
            column = self._columns[section]
            if role == Qt.ItemDataRole.DisplayRole:
                return column.header
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return column.get_alignment()
        return None

    # --- Checkbox selection helpers ---

    def is_checked(self, row: int) -> bool:
        """Check if a row is selected via checkbox."""
        return row in self._checked

    def set_checked(self, row: int, checked: bool) -> None:
        """Set checkbox state for a row."""
        if checked:
            self._checked.add(row)
        else:
            self._checked.discard(row)

        # Find checkbox column index
        for i, col in enumerate(self._columns):
            if col.column_type == ColumnType.CHECKBOX:
                idx = self.index(row, i)
                self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.CheckStateRole])
                break

        self.checked_changed.emit()

    def get_checked_rows(self) -> list[T]:
        """Return list of checked row data."""
        rows = self._rows()
        return [rows[i] for i in sorted(self._checked) if i < len(rows)]

    def get_checked_indices(self) -> set[int]:
        """Return set of checked row indices."""
        return self._checked.copy()

    def get_row_at(self, index: int) -> T | None:
        """Get row data at the given index."""
        rows = self._rows()
        if 0 <= index < len(rows):
            return rows[index]
        return None

    def select_all(self, checked: bool) -> None:
        """Select or deselect all rows."""
        if checked:
            self._checked = set(range(len(self._rows())))
        else:
            self._checked.clear()
        self.layoutChanged.emit()
        self.checked_changed.emit()

    def clear_checked(self) -> None:
        """Clear all checkbox selections."""
        self._checked.clear()
        self.layoutChanged.emit()
        self.checked_changed.emit()

    # --- Refresh ---

    def refresh(self) -> None:
        """Trigger full model refresh."""
        self.beginResetModel()
        self._invalidate_cache()
        # Keep checked items that are still valid
        row_count = len(self._rows())
        self._checked = {i for i in self._checked if i < row_count}
        self.endResetModel()
        self.checked_changed.emit()


class TableDelegate(QStyledItemDelegate):
    """Custom delegate for rendering and editing table cells.

    Handles:
    - Checkboxes: Centered, click to toggle
    - Spinboxes: Inline editing with SpinBox/DoubleSpinBox
    - Status: Colored text based on value
    """

    def __init__(self, columns: list[TableColumn], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._columns = columns

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        column = self._columns[index.column()]

        if column.column_type == ColumnType.CHECKBOX:
            self._paint_checkbox(painter, option, index)
        else:
            super().paint(painter, option, index)

    def _paint_checkbox(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        """Paint a centered checkbox."""
        # Draw background (attributes exist at runtime but not in type stubs)
        rect = option.rect  # type: ignore[attr-defined]

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)  # type: ignore[attr-defined]
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)  # type: ignore[attr-defined]
        if is_selected or is_hovered:
            painter.fillRect(rect, QColor(Colors.HOVER))

        # Draw checkbox
        check_opt = QStyleOptionButton()
        check_opt.initFrom(option.widget) if option.widget else None  # type: ignore[union-attr]
        check_opt.rect = rect  # type: ignore[assignment]
        check_opt.state = QStyle.StateFlag.State_Enabled  # type: ignore[assignment]

        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        if check_state == Qt.CheckState.Checked:
            check_opt.state |= QStyle.StateFlag.State_On  # type: ignore[assignment,operator]
        else:
            check_opt.state |= QStyle.StateFlag.State_Off  # type: ignore[assignment,operator]

        # Center the checkbox
        widget = getattr(option, "widget", None)
        style = widget.style() if widget else None
        if style and rect:
            check_size = style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth)
            x = rect.x() + (rect.width() - check_size) // 2
            check_opt.rect.setX(x)  # type: ignore[union-attr]
            check_opt.rect.setWidth(check_size)  # type: ignore[union-attr]
            style.drawControl(QStyle.ControlElement.CE_CheckBox, check_opt, painter)

    def createEditor(  # type: ignore[override]
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QWidget | None:
        column = self._columns[index.column()]

        if column.column_type == ColumnType.SPINBOX:
            editor = SpinBox(
                value=0,
                min_val=int(column.min_val),
                max_val=int(column.max_val),
                step=int(column.step),
                size=ControlSize.SM,
                parent=parent,
            )
            if column.suffix:
                editor.setSuffix(column.suffix)
            return editor

        if column.column_type == ColumnType.DOUBLE_SPINBOX:
            editor = DoubleSpinBox(
                value=0.0,
                min_val=column.min_val,
                max_val=column.max_val,
                step=column.step,
                decimals=column.decimals,
                size=ControlSize.SM,
                parent=parent,
            )
            if column.suffix:
                editor.setSuffix(column.suffix)
            return editor

        return super().createEditor(parent, option, index)

    def setEditorData(self, editor: QWidget, index: QModelIndex | QPersistentModelIndex) -> None:
        value = index.data(Qt.ItemDataRole.EditRole)
        if isinstance(editor, (SpinBox, DoubleSpinBox)):
            if value is not None:
                editor.setValue(value)
        else:
            super().setEditorData(editor, index)

    def setModelData(  # type: ignore[override]
        self, editor: QWidget, model: QAbstractTableModel, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        if isinstance(editor, (SpinBox, DoubleSpinBox)):
            model.setData(index, editor.value(), Qt.ItemDataRole.EditRole)
        else:
            super().setModelData(editor, model, index)

    def editorEvent(  # type: ignore[override]
        self,
        event: QMouseEvent,
        model: QAbstractTableModel,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Handle checkbox clicks without creating an editor."""
        column = self._columns[index.column()]

        if column.column_type == ColumnType.CHECKBOX and event.type() == event.Type.MouseButtonRelease:
            # Toggle checkbox
            current = index.data(Qt.ItemDataRole.CheckStateRole)
            new_state = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
            model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
            return True

        return super().editorEvent(event, model, option, index)


class Table(QWidget):
    """Styled table component for the Voxel Qt kit.

    Features:
    - Custom column definitions with type-specific delegates
    - Built-in checkbox selection with bulk operations
    - Row click and double-click signals
    - Consistent dark theme styling

    Usage:
        columns = [
            TableColumn(key="select", header="", column_type=ColumnType.CHECKBOX, width=40),
            TableColumn(key="name", header="Name", getter=lambda r, a: r.name),
        ]
        model = MyTableModel(data_source, columns)
        table = Table(model=model, columns=columns)
        table.row_clicked.connect(on_row_click)
    """

    row_clicked = Signal(int)  # Row index
    row_double_clicked = Signal(int)  # Row index
    selection_changed = Signal()  # Checkbox selection changed

    def __init__(
        self,
        model: TableModel,
        columns: list[TableColumn],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._columns = columns

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = vbox(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._view = QTableView()
        self._view.setModel(self._model)

        # Set delegate
        self._delegate = TableDelegate(self._columns, self._view)
        self._view.setItemDelegate(self._delegate)

        # Configure view - extended selection allows Shift+click and Ctrl+click
        self._view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._view.verticalHeader().setVisible(False)
        self._view.setShowGrid(False)
        self._view.setAlternatingRowColors(False)

        # Configure columns
        header = self._view.horizontalHeader()
        for i, col in enumerate(self._columns):
            if col.width:
                header.resizeSection(i, col.width)
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            else:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            header.setMinimumSectionSize(col.min_width)

        # Row height
        self._view.verticalHeader().setDefaultSectionSize(28)

        layout.addWidget(self._view)

    def _apply_style(self) -> None:
        """Apply dark theme styling."""
        self._view.setStyleSheet(f"""
            QTableView {{
                background-color: {Colors.BG_DARK};
                color: {Colors.TEXT};
                border: none;
                gridline-color: transparent;
                outline: none;
            }}
            QTableView::item {{
                padding: {Spacing.XS}px {Spacing.SM}px;
                border-bottom: 1px solid {Colors.BORDER};
            }}
            QTableView::item:selected {{
                background-color: {Colors.HOVER};
            }}
            QTableView::item:hover {{
                background-color: {Colors.HOVER};
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_MEDIUM};
                color: {Colors.TEXT_MUTED};
                border: none;
                border-bottom: 1px solid {Colors.BORDER};
                padding: {Spacing.XS}px {Spacing.SM}px;
                font-size: {FontSize.XS}px;
                text-transform: uppercase;
            }}
        """)

    def _connect_signals(self) -> None:
        self._view.clicked.connect(self._on_clicked)
        self._view.doubleClicked.connect(self._on_double_clicked)
        self._view.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _on_clicked(self, index: QModelIndex) -> None:
        """Handle row click."""
        if index.isValid():
            self.row_clicked.emit(index.row())

    def _on_double_clicked(self, index: QModelIndex) -> None:
        """Handle row double-click."""
        if index.isValid():
            self.row_double_clicked.emit(index.row())

    def _on_selection_changed(self) -> None:
        """Handle selection model change."""
        self.selection_changed.emit()

    # --- Public API ---

    def get_selected_rows(self) -> list[int]:
        """Get list of selected row indices."""
        return [idx.row() for idx in self._view.selectionModel().selectedRows()]

    def get_selected_count(self) -> int:
        """Get number of selected rows."""
        return len(self._view.selectionModel().selectedRows())

    def clear_selection(self) -> None:
        """Clear row selection."""
        self._view.clearSelection()

    @property
    def model(self) -> TableModel:
        """Get the table model."""
        return self._model

    @property
    def view(self) -> QTableView:
        """Get the underlying QTableView."""
        return self._view


class TableToolbar(QWidget):
    """Toolbar with filter dropdown and bulk action buttons.

    Usage:
        toolbar = TableToolbar()
        toolbar.add_filter("mode", [("all", "All"), ("with_stack", "With Stack")])
        toolbar.add_action("delete", "Delete", icon="mdi.trash-can-outline",
                          color=Colors.ERROR, visible_when_selected=True)
        toolbar.filter_changed.connect(on_filter_change)
        toolbar.action_triggered.connect(on_action)
    """

    filter_changed = Signal(str, object)  # filter_key, value
    action_triggered = Signal(str)  # action_key

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filters: dict[str, Select] = {}
        self._actions: dict[str, ToolButton] = {}
        self._selected_actions: list[str] = []  # Actions to show only when items selected
        self._selected_count = 0

        self._setup_ui()

    def _setup_ui(self) -> None:
        self._layout_box = Box.hstack(spacing=Spacing.SM)
        self._layout_box.add(Stretch())  # Push actions to the right

        # Selection count label (hidden by default)
        self._count_label = Text.muted("0 selected", size=FontSize.XS)
        self._count_label.hide()

        layout = vbox(self, spacing=0, margins=(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS))
        layout.addWidget(self._layout_box)

    def add_filter(
        self,
        key: str,
        options: list[tuple[Any, str]],
        default: Any | None = None,
    ) -> None:
        """Add a filter dropdown.

        Args:
            key: Unique identifier for the filter
            options: List of (value, label) tuples
            default: Default selected value (uses first option if None)
        """
        select = Select(options=options, value=default or options[0][0], size=ControlSize.SM)
        select.value_changed.connect(lambda v: self.filter_changed.emit(key, v))

        self._filters[key] = select

        # Insert before the stretch
        layout = self._layout_box.layout()
        if layout is not None:
            layout.insertWidget(len(self._filters) - 1, select)  # type: ignore[union-attr]

    def add_action(
        self,
        key: str,
        label: str,
        icon: str | None = None,
        color: str | None = None,
        visible_when_selected: bool = False,
    ) -> None:
        """Add an action button.

        Args:
            key: Unique identifier for the action
            label: Button label (used as tooltip if icon provided)
            icon: Optional MDI icon name
            color: Optional button color
            visible_when_selected: Only show when items are selected
        """
        if icon:
            btn = ToolButton(icon, color=color or Colors.TEXT, size=ControlSize.SM)
            btn.setToolTip(label)
        else:
            btn = ToolButton(label, color=color or Colors.TEXT, size=ControlSize.SM)

        btn.clicked.connect(lambda: self.action_triggered.emit(key))

        self._actions[key] = btn

        if visible_when_selected:
            self._selected_actions.append(key)
            btn.hide()

        # Add count label before first selected action
        if visible_when_selected and len(self._selected_actions) == 1:
            self._layout_box.add(self._count_label)

        self._layout_box.add(btn)

    def set_selected_count(self, count: int) -> None:
        """Update selected count display and button visibility."""
        self._selected_count = count

        # Update count label
        if count > 0:
            self._count_label.setText(f"{count} selected")
            self._count_label.show()
        else:
            self._count_label.hide()

        # Show/hide selected-only actions
        for key in self._selected_actions:
            self._actions[key].setVisible(count > 0)

    def get_filter_value(self, key: str) -> Any:
        """Get current value of a filter."""
        if key in self._filters:
            return self._filters[key].value()
        return None
