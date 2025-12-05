"""Generic input widgets for device control."""

from spim_widgets.ui.input.binding import FieldBinder, ValueBinding, ValueWatcher
from spim_widgets.ui.input.checkbox import VCheckBox, VSwitch
from spim_widgets.ui.input.label import LiveValueLabel, VLabel
from spim_widgets.ui.input.number import VNumberInput
from spim_widgets.ui.input.select import VComboBox, VSelect
from spim_widgets.ui.input.text import VLineEdit, VTextInput
from spim_widgets.ui.input.toggle import VToggle

__all__ = [
    # Binding
    "FieldBinder",
    "ValueBinding",
    "ValueWatcher",
    # Checkbox
    "VCheckBox",
    "VSwitch",
    # Label
    "LiveValueLabel",
    "VLabel",
    # Number
    "VNumberInput",
    # Select
    "VComboBox",
    "VSelect",
    # Text
    "VLineEdit",
    "VTextInput",
    # Toggle
    "VToggle",
]
