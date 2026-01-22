from collections.abc import Mapping
from enum import Enum

from PySide6.QtWidgets import QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from spim_widgets.ui.input.checkbox import VSwitch
from spim_widgets.ui.input.label import VLabel
from spim_widgets.ui.input.number import VNumberInput
from spim_widgets.ui.input.select import VSelect
from spim_widgets.ui.input.text import VTextInput
from spim_widgets.ui.input.toggle import VToggle


class FlowDirection(Enum):
    """Simplified layout options that are actually useful."""

    VERTICAL = "vertical"  # Vertical stack with labels on top (classic forms)
    HORIZONTAL = "horizontal"  # Horizontal row with labels on top (toolbars)
    FORM = "form"  # Vertical with labels on left (Qt optimized)
    GRID = "grid"  # 2D grid layout with configurable columns


type VInputComponent = VSelect | VTextInput | VNumberInput | VToggle | VSwitch


def create_input_group(
    inputs: Mapping[str, VInputComponent],
    flow: FlowDirection = FlowDirection.FORM,
    spacing: int = 8,
    margins: int = 10,
    grid_columns: int = 2,
) -> QWidget:
    """Create a group of labeled input widgets with simplified, useful layout options.

    Args:
        inputs: Dictionary of label->input pairs
        flow: Layout type - each has a specific, useful purpose:
            - VERTICAL: Labels on top, widgets stacked vertically (classic forms)
            - HORIZONTAL: Labels on top, widgets in a row (toolbars)
            - FORM: Labels on left, widgets stacked (Qt optimized for forms)
            - GRID: Labels on top, 2D grid layout
        spacing: Space between elements in pixels
        margins: Margin around the entire group in pixels
        grid_columns: Number of columns when using grid layout

    """
    group = QWidget()

    widgets = {
        label: input_widget if isinstance(input_widget, QWidget) else input_widget.widget
        for label, input_widget in inputs.items()
    }

    def add_vertical_widgets() -> QVBoxLayout:
        """Add widgets to a QVBoxLayout."""
        layout = QVBoxLayout(group)
        for label_text, widget in widgets.items():
            layout.addWidget(VLabel(label_text))
            layout.addWidget(widget)
        return layout

    def add_horizontal_widgets() -> QHBoxLayout:
        """Add widgets to a QHBoxLayout."""
        layout = QHBoxLayout(group)
        for label_text, widget in widgets.items():
            pair_container = QWidget()
            pair_layout = QVBoxLayout(pair_container)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(4)
            pair_layout.addWidget(VLabel(label_text))
            pair_layout.addWidget(widget)
            layout.addWidget(pair_container)
        return layout

    def add_grid_widgets() -> QGridLayout:
        """Add widgets to a QGridLayout."""
        layout = QGridLayout(group)
        row = 0
        col = 0
        for label_text, widget in widgets.items():
            layout.addWidget(VLabel(label_text), row * 2, col)
            layout.addWidget(widget, row * 2 + 1, col)
            col += 1
            if col >= grid_columns:
                col = 0
                row += 1
        return layout

    def add_form_widgets() -> QFormLayout:
        """Add widgets to a QFormLayout."""
        layout = QFormLayout(group)
        for label_text, widget in widgets.items():
            layout.addRow(VLabel(label_text), widget)
        return layout

    if flow == FlowDirection.VERTICAL:
        layout = add_vertical_widgets()
    elif flow == FlowDirection.HORIZONTAL:
        layout = add_horizontal_widgets()
    elif flow == FlowDirection.GRID:
        layout = add_grid_widgets()
    else:
        layout = add_form_widgets()

    layout.setSpacing(spacing)
    layout.setContentsMargins(margins, margins, margins, margins)
    group.setLayout(layout)
    return group
