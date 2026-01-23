"""Select/ComboBox input primitives."""

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QWidget

from voxel_qt.ui.theme import Colors, FontSize, Size


class Select(QComboBox):
    """A styled combobox for selecting from a list of options.

    Supports both string options and options with separate display text and values.

    Usage:
        # Simple string options
        Select(options=["Option 1", "Option 2", "Option 3"])

        # With initial value
        Select(options=["Low", "Medium", "High"], value="Medium")

        # With format function for display
        Select(options=[1, 2, 4], value=2, format_option=lambda x: f"{x}x{x}")

        # Connect to value changes
        select.value_changed.connect(lambda v: print(f"Selected: {v}"))
    """

    # Signal emitted when value changes (emits the actual value, not display text)
    value_changed = Signal(object)

    def __init__(
        self,
        options: Sequence[Any] | None = None,
        value: Any = None,
        format_option: Callable[[Any], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the select widget.

        Args:
            options: List of options (values). Can be strings, ints, etc.
            value: Initial selected value.
            format_option: Optional function to format values for display.
                           If None, str() is used.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._format_option = format_option or str
        self._values: list[Any] = []

        self._apply_style()

        if options:
            self.set_options(options, value)

        # Connect internal signal to our typed signal
        self.currentIndexChanged.connect(self._on_index_changed)

    def _apply_style(self) -> None:
        """Apply minimal styling - mostly use Qt defaults."""
        self.setStyleSheet(f"""
            QComboBox {{
                font-size: {FontSize.SM}px;
                min-height: {Size.INPUT_HEIGHT}px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.BG_MEDIUM};
                selection-background-color: {Colors.ACCENT};
            }}
        """)

    def _on_index_changed(self, index: int) -> None:
        """Handle internal index change and emit typed value."""
        if 0 <= index < len(self._values):
            self.value_changed.emit(self._values[index])

    def set_options(self, options: Sequence[Any], value: Any = None) -> None:
        """Set the available options.

        Args:
            options: List of option values.
            value: Value to select after setting options.
        """
        # Block signals while updating
        self.blockSignals(True)

        self.clear()
        self._values = list(options)

        for opt in options:
            display_text = self._format_option(opt)
            self.addItem(display_text)

        # Set initial value if provided
        if value is not None and value in self._values:
            self.setCurrentIndex(self._values.index(value))

        self.blockSignals(False)

    def get_value(self) -> Any | None:
        """Get the currently selected value.

        Returns:
            The selected value, or None if no selection.
        """
        index = self.currentIndex()
        if 0 <= index < len(self._values):
            return self._values[index]
        return None

    def set_value(self, value: Any) -> None:
        """Set the selected value.

        Args:
            value: Value to select. Must be in the options list.
        """
        if value in self._values:
            self.setCurrentIndex(self._values.index(value))

    # Alias for Qt-like API
    value = property(get_value, set_value)
