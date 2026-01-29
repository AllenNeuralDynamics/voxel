"""Select/ComboBox input primitives."""

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QWidget

from voxel_qt.ui.kit.theme import Colors, ControlSize

# Option can be:
# - str: value = label, no description
# - (value, label): explicit label, no description
# - (value, label, description): full option with tooltip
type SelectOption[T: str | int | float] = T | tuple[T, str] | tuple[T, str, str]


class Select(QComboBox):
    """A styled combobox for selecting from a list of options.

    Options can be simple strings or tuples with (value, label, description).

    Usage:
        # Simple string options (value = label)
        Select(options=["low", "medium", "high"])

        # With display formatter
        Select(options=[1, 2, 4], display_fmt=lambda x: f"{x}x magnification")

        # With explicit labels
        Select(options=[("low", "Low Quality"), ("high", "High Quality")])

        # With descriptions (shown as tooltips)
        Select(options=[
            ("low", "Low Quality", "Best for slow connections"),
            ("high", "High Quality", "Maximum resolution"),
        ])

        # Connect to value changes
        select.value_changed.connect(lambda v: print(f"Selected: {v}"))
    """

    value_changed = Signal(object)

    def __init__(
        self,
        options: Sequence[SelectOption] | None = None,
        value: Any = None,
        display_fmt: Callable[[Any], str] | None = None,
        size: ControlSize = ControlSize.MD,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the select widget.

        Args:
            options: List of options. Can be strings or tuples of (value, label, description).
            value: Initial selected value.
            display_fmt: Function to format values for display when label not provided.
            size: Size preset for the widget.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._display_fmt = display_fmt
        self._values: list[Any] = []
        self._size = size

        self._apply_style()

        if options:
            self.set_options(options, value)

        self.currentIndexChanged.connect(self._on_index_changed)

    def _apply_style(self) -> None:
        """Apply minimal styling for dark theme."""
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {Colors.BG_LIGHT};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: {self._size.radius}px;
                font-size: {self._size.font}px;
                height: {self._size.h}px;
                padding: 0 {self._size.px}px;
            }}
            QComboBox:hover {{
                border-color: {Colors.BORDER_FOCUS};
            }}
            QComboBox:focus {{
                border-color: {Colors.ACCENT};
            }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.BG_MEDIUM};
                border: 1px solid {Colors.BORDER};
                border-radius: {self._size.radius}px;
                selection-background-color: {Colors.ACCENT};
            }}
        """)

    def _parse_option(self, opt: SelectOption) -> tuple[Any, str | None, str | None]:
        """Parse an option into (value, label, description).

        If label is None, it will be derived from display_fmt or str(value).
        """
        if isinstance(opt, tuple) and len(opt) >= 2:
            if len(opt) == 2:
                val, label = opt
                return val, label, None
            val, label, desc = opt[0], opt[1], opt[2]
            return val, label, desc
        # Non-tuple value - label will be derived
        return opt, None, None

    def _on_index_changed(self, index: int) -> None:
        """Handle internal index change and emit typed value."""
        if 0 <= index < len(self._values):
            self.value_changed.emit(self._values[index])

    def set_options(self, options: Sequence[SelectOption], value: Any = None) -> None:
        """Set the available options.

        Args:
            options: List of options. Can be values or tuples of (value, label[, description]).
            value: Value to select after setting options.
        """
        self.blockSignals(True)
        self.clear()
        self._values = []

        for opt in options:
            val, label, desc = self._parse_option(opt)
            self._values.append(val)

            # Derive label if not provided
            if label is None:
                label = self._display_fmt(val) if self._display_fmt else str(val)

            self.addItem(label)

            # Store description as tooltip
            if desc:
                self.setItemData(self.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)

        if value is not None and value in self._values:
            self.setCurrentIndex(self._values.index(value))

        self.blockSignals(False)

    def get_value(self) -> Any | None:
        """Get the currently selected value."""
        index = self.currentIndex()
        if 0 <= index < len(self._values):
            return self._values[index]
        return None

    def set_value(self, value: Any) -> None:
        """Set the selected value."""
        if value in self._values:
            self.setCurrentIndex(self._values.index(value))

    value = property(get_value, set_value)
