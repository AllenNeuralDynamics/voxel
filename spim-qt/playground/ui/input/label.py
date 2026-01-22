import logging
from collections.abc import Callable

from PySide6.QtWidgets import QLabel, QWidget

from spim_widgets.ui.input.binding import ValueWatcher


class VLabel(QLabel):
    """A styled label component with consistent styling."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent=parent)
        self._apply_styles()

    def _apply_styles(self):
        """Apply consistent styling to the label."""
        style = """
            QLabel {
                font-weight: bold;
                margin-bottom: 4px;
            }
        """
        self.setStyleSheet(style)


class LiveValueLabel[T: str | int | float]:
    """Atomic component for displaying a polled read-only value with optional prefix/suffix using composition."""

    def __init__(
        self,
        getter: Callable[[], T],
        prefix: str = "",
        suffix: str = "",
        format_func: Callable[[T], str] | None = None,
        poll_interval: int = 1000,
        parent: QWidget | None = None,
    ):
        self._getter = getter
        self._prefix = prefix
        self._suffix = suffix
        self._format_func = format_func or str
        self.log = logging.getLogger(f"LiveLabel[{id(self)}]")

        # Create the label widget
        self._label = VLabel(parent=parent)

        self._value_watcher = ValueWatcher(callback=self.update_value, interval=poll_interval, parent=parent)

    @property
    def widget(self) -> VLabel:
        """Access to the underlying VLabel widget for layout and styling."""
        return self._label

    @property
    def text(self) -> str:
        """Get the current text of the label."""
        return self._label.text()

    def update_value(self):
        """Update the displayed value by polling the getter."""
        try:
            raw_value = self._getter()
            formatted_value = self._format_func(raw_value)
            display_text = f"{self._prefix}{formatted_value}{self._suffix}"
            self._label.setText(display_text)
        except Exception as e:
            self.log.exception("Error updating label value")
            self._label.setText(f"{self._prefix}Error: {e}{self._suffix}")

    def start_polling(self):
        """Start polling."""
        self._value_watcher.start()

    def stop_polling(self):
        """Stop polling."""
        self._value_watcher.stop()

    def refresh(self):
        """Immediately update the value (same as update_value)."""
        self.update_value()

    # Forward common QLabel methods for convenience
    def setAlignment(self, alignment) -> None:
        """Set the alignment of the label."""
        self._label.setAlignment(alignment)

    def setStyleSheet(self, style: str) -> None:
        """Set the style sheet of the label."""
        self._label.setStyleSheet(style)

    def setFont(self, font) -> None:
        """Set the font of the label."""
        self._label.setFont(font)
