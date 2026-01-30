"""Form builders for creating labeled field layouts."""

from dataclasses import dataclass
from typing import Self

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QGridLayout, QWidget

from .text import Text
from .theme import Colors, Spacing


@dataclass
class Field:
    """A labeled form field entry."""

    label: str
    widget: QWidget
    span: int = 1  # Number of widget columns to span


class GridFormBuilder:
    """Fluent builder for grid-based form layouts with proper column alignment.

    Uses QGridLayout with alternating label/widget columns for consistent alignment.
    Supports spanning for widgets that need more space.

    Usage:
        form = (GridFormBuilder()
            .row(Field("Exposure", HBox(spinbox, slider), span=3))
            .row(Field("Format", select), Field("Binning", select))
            .row(Field("Offset X", spin), Field("Offset Y", spin))
            .build())
    """

    def __init__(self, columns: int = 2, spacing: int = Spacing.MD):
        """Initialize the grid form builder.

        Args:
            columns: Number of Field columns (each Field = label + widget).
            spacing: Spacing between grid cells.
        """
        self._columns = columns
        self._widget = QWidget()
        self._widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._layout = QGridLayout(self._widget)
        self._layout.setSpacing(spacing)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._current_row = 0

        # Set column stretches: labels don't stretch, widgets do
        for i in range(columns):
            label_col = i * 2
            widget_col = i * 2 + 1
            self._layout.setColumnStretch(label_col, 0)  # Label: no stretch
            self._layout.setColumnStretch(widget_col, 1)  # Widget: stretch

    def row(self, *fields: Field) -> Self:
        """Add a row of fields.

        Args:
            fields: Field entries. Each Field's span determines how many
                    widget columns it occupies.

        Usage:
            .row(Field("Exposure", widget, span=3))  # Spans 3 widget columns
            .row(Field("Format", select), Field("Binning", select))
        """
        col = 0
        for field in fields:
            label_col = col * 2
            widget_col = col * 2 + 1

            # Add label
            label = Text(field.label)
            self._layout.addWidget(label, self._current_row, label_col)

            # Calculate widget column span (each span unit = 2 grid columns - 1 for the label gaps)
            # span=1: just widget_col (1 grid column)
            # span=2: widget_col + next label_col + next widget_col (3 grid columns)
            # span=3: 5 grid columns, etc.
            grid_span = field.span * 2 - 1
            self._layout.addWidget(field.widget, self._current_row, widget_col, 1, grid_span)

            col += field.span

        self._current_row += 1
        return self

    def build(self) -> QWidget:
        """Build and return the form widget."""
        return self._widget


class FormBuilder:
    """Fluent builder for simple form layouts using QFormLayout.

    For multi-column forms, use GridFormBuilder instead.

    Usage:
        form = (FormBuilder()
            .header("Settings")
            .field("Name", self._name_input)
            .field("Value", self._value_input)
            .build())
    """

    def __init__(self, spacing: int = Spacing.MD):
        self._widget = QWidget()
        self._widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._layout = QFormLayout(self._widget)
        self._layout.setSpacing(spacing)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def header(self, title: str) -> Self:
        """Add a section header."""
        label = Text(title)
        label.setStyleSheet(f"font-weight: bold; color: {Colors.TEXT_MUTED}; margin-top: {Spacing.MD}px;")
        self._layout.addRow(label)
        return self

    def field(self, label: str, widget: QWidget) -> Self:
        """Add a labeled field (label left, widget right)."""
        self._layout.addRow(label, widget)
        return self

    def build(self) -> QWidget:
        """Build and return the form widget."""
        return self._widget
