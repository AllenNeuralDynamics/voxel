import logging
from collections.abc import Callable

from PySide6.QtWidgets import QCheckBox, QVBoxLayout, QWidget


class VCheckBox(QCheckBox):
    """A styled checkbox component - basic styling only."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self._apply_styles()

    def _apply_styles(self):
        """Apply switch-like styling to the checkbox."""
        style = """
            QCheckBox {
                font-size: 11px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 40px;
                height: 20px;
                border-radius: 5px;
            }
            QCheckBox::indicator:checked {
                background-color: #0078D4;
                border-color: #0078D4;
            }
            QCheckBox::indicator:hover {
                border-color: #999999;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #106EBE;
                border-color: #106EBE;
            }
        """
        self.setStyleSheet(style)


class VSwitch(QWidget):
    """A functional switch widget that wraps VCheckBox with functionality."""

    def __init__(
        self,
        text: str = "",
        getter: Callable[[], bool] | None = None,
        setter: Callable[[bool], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self.text = text
        self.getter = getter
        self.setter = setter
        self.log = logging.getLogger(f"VSwitch[{id(self)}]")
        self._setup_ui()

    @property
    def widget(self) -> QWidget:
        """Get the underlying widget for this input component."""
        return self

    def _setup_ui(self):
        """Set up the user interface with just a styled checkbox."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # No margins, let parent control spacing
        layout.setSpacing(0)

        # Create styled checkbox
        self.checkbox = VCheckBox()

        # Set text if provided
        if self.text:
            self.checkbox.setText(self.text)

        # Set initial value from getter if provided
        if self.getter:
            try:
                initial_value = self.getter()
                self.checkbox.setChecked(initial_value)
            except Exception:
                # If getter fails, just continue without setting value
                self.log.exception("Error calling getter for initial value:")

        # Connect callback if provided
        if self.setter:
            self.checkbox.toggled.connect(self._on_toggled)

        layout.addWidget(self.checkbox)

    def _on_toggled(self, checked: bool):
        """Handle toggle events."""
        if self.setter:
            self.setter(checked)

    def isChecked(self) -> bool:
        """Get the current checked state."""
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:
        """Set the checked state."""
        self.checkbox.setChecked(checked)
