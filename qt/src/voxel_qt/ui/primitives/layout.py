"""Layout primitives for composable UI construction."""

from __future__ import annotations

from typing import Self

from PySide6.QtWidgets import QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget
from voxel_qt.ui.primitives.display.label import Label
from voxel_qt.ui.theme import Colors


class HStack(QWidget):
    """Horizontal stack of widgets.

    Usage:
        HStack(self._spinbox, self._button)
        HStack(self._a, self._b, self._c, spacing=8)
    """

    def __init__(self, *widgets: QWidget, spacing: int = 4, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        for w in widgets:
            layout.addWidget(w)


class VStack(QWidget):
    """Vertical stack of widgets.

    Usage:
        VStack(self._label, self._input)
        VStack(*form_rows, spacing=8)
    """

    def __init__(self, *widgets: QWidget, spacing: int = 4, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        for w in widgets:
            layout.addWidget(w)


class Grid(QWidget):
    """Grid layout of widgets.

    Arranges widgets in a grid with specified number of columns.
    Widgets fill left-to-right, top-to-bottom.

    Usage:
        Grid(w1, w2, w3, w4, columns=2)  # 2x2 grid
        Grid(*cards, columns=3, spacing=8)
    """

    def __init__(
        self,
        *widgets: QWidget,
        columns: int = 2,
        spacing: int = 8,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)

        for col in range(columns):
            layout.setColumnStretch(col, 1)

        for i, widget in enumerate(widgets):
            row = i // columns
            col = i % columns
            layout.addWidget(widget, row, col)

        if widgets:
            last_row = (len(widgets) - 1) // columns
            layout.setRowStretch(last_row + 1, 1)


class Field(QWidget):
    """Vertical field: label on top, widget below.

    Usage:
        Field("Medium", self._medium_input)
        HStack(Field("X", self._x), Field("Y", self._y), Field("Z", self._z))
    """

    def __init__(
        self,
        label: str,
        widget: QWidget,
        spacing: int = 4,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        layout.addWidget(Label(label))
        layout.addWidget(widget)

        self.widget = widget


class InfoRow(QWidget):
    """Read-only label + value row for displaying info.

    Usage:
        InfoRow("UID:", "camera-01")
        InfoRow("Type:", instrument_type, stretch=False)
    """

    def __init__(
        self,
        label: str,
        value: str,
        stretch: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(Label(label))

        self._value_label = Label(value)
        self._value_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self._value_label)

        if stretch:
            layout.addStretch()

    def set_value(self, value: str) -> None:
        """Update the displayed value."""
        self._value_label.setText(value)


class FormBuilder:
    """Fluent builder for horizontal form layouts using QFormLayout.

    Usage:
        form = (FormBuilder()
            .header("Grid Configuration")
            .field("Rows", self._rows)
            .field("Cols", self._columns)
            .field("Z start", HStack(self._z_start, self._z_start_fov_btn))
            .build())
    """

    def __init__(self, spacing: int = 8):
        self._widget = QWidget()
        self._layout = QFormLayout(self._widget)
        self._layout.setSpacing(spacing)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def header(self, title: str) -> Self:
        """Add a section header."""
        label = Label(title)
        label.setStyleSheet(f"font-weight: bold; color: {Colors.TEXT_MUTED}; margin-top: 8px;")
        self._layout.addRow(label)
        return self

    def field(self, label: str, widget: QWidget) -> Self:
        """Add a horizontal field (label left, widget right)."""
        self._layout.addRow(label, widget)
        return self

    def build(self) -> QWidget:
        """Build and return the form widget."""
        return self._widget
