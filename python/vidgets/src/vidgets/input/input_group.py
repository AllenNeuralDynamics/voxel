from collections.abc import Mapping
from enum import Enum

from PySide6.QtWidgets import QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget
from vidgets.input.checkbox import VSwitch
from vidgets.input.label import VLabel
from vidgets.input.number import VNumberInput
from vidgets.input.select import VSelect
from vidgets.input.text import VTextInput
from vidgets.input.toggle import VToggle


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
    """
    Create a group of labeled input widgets with simplified, useful layout options.

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

    widgets = {label: input if isinstance(input, QWidget) else input.widget for label, input in inputs.items()}

    # Choose layout and label positioning based on flow direction
    if flow == FlowDirection.VERTICAL:
        layout = QVBoxLayout(group)
    elif flow == FlowDirection.HORIZONTAL:
        layout = QHBoxLayout(group)
    elif flow == FlowDirection.GRID:
        layout = QGridLayout(group)
    else:
        layout = QFormLayout(group)  # Default to FORM layout as it's the most commonly useful

    # Configure layout properties
    layout.setSpacing(spacing)
    layout.setContentsMargins(margins, margins, margins, margins)

    # Add widgets based on layout type
    if isinstance(layout, QFormLayout):
        for label_text, widget in widgets.items():
            layout.addRow(VLabel(label_text), widget)

    elif isinstance(layout, QGridLayout):
        # Grid layout with labels on top
        row = 0
        col = 0
        for label_text, widget in widgets.items():
            layout.addWidget(VLabel(label_text), row * 2, col)
            layout.addWidget(widget, row * 2 + 1, col)

            col += 1
            if col >= grid_columns:
                col = 0
                row += 1

    else:
        # Linear layouts (vertical/horizontal) with labels on top
        for label_text, widget in widgets.items():
            if flow == FlowDirection.HORIZONTAL:
                # For horizontal layout, create label-widget pairs in containers
                pair_container = QWidget()
                pair_layout = QVBoxLayout(pair_container)
                pair_layout.setContentsMargins(0, 0, 0, 0)
                pair_layout.setSpacing(4)
                pair_layout.addWidget(VLabel(label_text))
                pair_layout.addWidget(widget)
                layout.addWidget(pair_container)
            else:
                # Vertical layout - just stack labels and widgets
                layout.addWidget(VLabel(label_text))
                layout.addWidget(widget)

    return group
