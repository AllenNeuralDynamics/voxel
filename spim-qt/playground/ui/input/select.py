import logging
from collections.abc import Callable

from PySide6.QtWidgets import QComboBox, QVBoxLayout, QWidget


class VComboBox(QComboBox):
    """A styled combobox component with consistent styling."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self._apply_styles()

    def _apply_styles(self):
        """Apply consistent styling to the combobox."""
        style = """
            QComboBox {
                border-radius: 4px;
                padding: 6px 8px;
                min-height: 20px;
            }
            QComboBox QAbstractItemView {
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px 12px;
                min-height: 20px;
            }
        """
        self.setStyleSheet(style)


class VSelect(QWidget):
    """A simple select widget with just a styled combobox."""

    def __init__(
        self,
        options: list[str],
        getter: Callable[[], str] | None = None,
        setter: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self.options = options
        self.getter = getter
        self.setter = setter
        self.log = logging.getLogger(f"VSelect[{id(self)}]")
        self._setup_ui()

    @property
    def widget(self) -> QWidget:
        """Get the underlying widget for this input component."""
        return self

    def _setup_ui(self):
        """Set up the user interface with just a combobox."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # No margins, let parent control spacing
        layout.setSpacing(0)

        # Create styled combobox
        self.combobox = VComboBox()
        self.combobox.addItems(self.options)

        # Connect callback if provided
        if self.setter:
            self.combobox.currentTextChanged.connect(self._on_selection_changed)

        # Set initial value from getter if provided
        if self.getter:
            try:
                initial_value = self.getter()
                if initial_value in self.options:
                    self.combobox.setCurrentText(initial_value)
            except Exception:
                self.log.exception("Error getting initial value")
                # If getter fails, just continue without setting value

        layout.addWidget(self.combobox)

        self.setLayout(layout)

    def _on_selection_changed(self, text: str):
        """Handle combobox selection changes."""
        if self.setter:
            self.setter(text)

    def get_current_selection(self) -> str:
        """Get the currently selected option."""
        return self.combobox.currentText()

    def set_current_selection(self, text: str):
        """Set the currently selected option."""
        index = self.combobox.findText(text)
        if index >= 0:
            self.combobox.setCurrentIndex(index)

    def update_options(self, options: list[str]):
        """Update the available options in the combobox."""
        self.options = options
        current_text = self.combobox.currentText()
        self.combobox.clear()
        self.combobox.addItems(options)

        # Try to restore the previous selection if it still exists
        index = self.combobox.findText(current_text)
        if index >= 0:
            self.combobox.setCurrentIndex(index)
