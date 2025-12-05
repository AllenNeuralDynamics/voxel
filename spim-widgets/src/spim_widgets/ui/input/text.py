import logging
from collections.abc import Callable

from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget


class VLineEdit(QLineEdit):
    """A styled text input component - basic styling only."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self._apply_styles()

    def _apply_styles(self):
        """Apply consistent styling to the text input."""
        style = """
            QLineEdit {
                border: 2px solid #CCCCCC;
                border-radius: 4px;
                padding: 6px 8px;
                min-height: 20px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #0078D4;
                outline: none;
            }
            QLineEdit:hover {
                border-color: #999999;
            }
        """
        self.setStyleSheet(style)


class VTextInput(QWidget):
    """A functional text input widget that wraps VLineEdit with functionality."""

    def __init__(
        self,
        placeholder: str = "",
        getter: Callable[[], str] | None = None,
        setter: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self.placeholder = placeholder
        self.getter = getter
        self.setter = setter
        self.log = logging.getLogger(f"VTextInput[{id(self)}]")
        self._setup_ui()

    def _setup_ui(self):
        """Set up the user interface with just a styled line edit."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # No margins, let parent control spacing
        layout.setSpacing(0)

        # Create styled line edit
        self.line_edit = VLineEdit()

        # Set placeholder if provided
        if self.placeholder:
            self.line_edit.setPlaceholderText(self.placeholder)

        # Set initial value from getter if provided
        if self.getter:
            try:
                initial_value = self.getter()
                self.line_edit.setText(initial_value)
            except Exception:
                self.log.exception("Error getting initial value")
                # If getter fails, just continue without setting value

        # Connect callback if provided
        if self.setter:
            self.line_edit.textChanged.connect(self._on_text_changed)

        layout.addWidget(self.line_edit)

    def _on_text_changed(self, text: str):
        """Handle text change events."""
        if self.setter:
            self.setter(text)

    def text(self) -> str:
        """Get the current text value."""
        return self.line_edit.text()

    def setText(self, text: str) -> None:
        """Set the text value."""
        self.line_edit.setText(text)
