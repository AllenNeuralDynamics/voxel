from collections.abc import Callable

from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QWidget

from spim_widgets.ui.input.binding import BoundInput


class VNumberInput[T: int | float](BoundInput[T, QSpinBox | QDoubleSpinBox]):
    """Generic SpinBox bound to hardware that automatically chooses QSpinBox or QDoubleSpinBox.

    Automatically selects the appropriate widget type:
    - BoundSpinBox[int] creates a QSpinBox for integer values
    - BoundSpinBox[float] creates a QDoubleSpinBox for floating-point values

    Optimized for responsive numeric input:
    - Lower debounce delay (300ms) since spinboxes have discrete values
    - Shorter settle delay (100ms) since numeric hardware typically responds quickly
    - No continuous monitoring by default (user-driven input)
    """

    def __init__(
        self,
        getter: Callable[[], T],
        onchange: Callable[[T], None],
        *,
        parent: QWidget,
        min_value: T | None = None,
        max_value: T | None = None,
        decimals: int = 2,
        debounce_delay: int = 300,
        watch_interval: int | None = None,
        settle_delay: int = 100,
    ) -> None:
        super().__init__(
            getter=getter,
            setter=onchange,
            debounce_delay=debounce_delay,
            watch_interval=watch_interval,
            settle_delay=settle_delay,
        )

        # Determine widget type based on the getter return type
        sample_value = self._binding.get_value()

        if isinstance(sample_value, float):
            self._spinbox = QDoubleSpinBox(parent)
            self._spinbox.setRange(
                float(min_value) if min_value is not None else float("-inf"),
                float(max_value) if max_value is not None else float("inf"),
            )
            self._spinbox.setDecimals(decimals if decimals is not None else 2)
            self._spinbox.setValue(float(sample_value))
        elif isinstance(sample_value, int):
            self._spinbox = QSpinBox(parent)
            self._spinbox.setRange(
                int(min_value) if min_value is not None else -1000,
                int(max_value) if max_value is not None else 1000,
            )
            self._spinbox.setValue(int(sample_value))
        else:
            msg = f"Unsupported type: {type(sample_value)}. Sample value: {sample_value}"
            raise TypeError(msg)

        # Connect spinbox to binding (user input -> hardware)
        self._spinbox.valueChanged.connect(self._binding.set_value)
        self._binding.setParent(self._spinbox)

    def _update_display(self, value: T) -> None:
        """Update spinbox display when binding value changes (from external sources)."""
        self._spinbox.blockSignals(True)
        if isinstance(self._spinbox, QDoubleSpinBox):
            self._spinbox.setValue(float(value))
        else:
            self._spinbox.setValue(int(value))
        self._spinbox.blockSignals(False)

    @property
    def widget(self) -> QSpinBox | QDoubleSpinBox:
        """Access to the underlying spinbox widget for layout and styling."""
        return self._spinbox

    # Forward common spinbox methods for convenience
    def setRange(self, min_val: T, max_val: T) -> None:
        """Set the range of the spinbox."""
        if isinstance(self._spinbox, QDoubleSpinBox):
            self._spinbox.setRange(float(min_val), float(max_val))
        else:
            self._spinbox.setRange(int(min_val), int(max_val))

    def setSuffix(self, suffix: str) -> None:
        """Set the suffix of the spinbox."""
        self._spinbox.setSuffix(suffix)

    def setPrefix(self, prefix: str) -> None:
        """Set the prefix of the spinbox."""
        self._spinbox.setPrefix(prefix)

    def setSingleStep(self, step: T) -> None:
        """Set the single step of the spinbox."""
        if isinstance(self._spinbox, QDoubleSpinBox):
            self._spinbox.setSingleStep(float(step))
        else:
            self._spinbox.setSingleStep(int(step))

    # Additional methods specific to QDoubleSpinBox
    def setDecimals(self, decimals: int) -> None:
        """Set the number of decimal places (QDoubleSpinBox only)."""
        if isinstance(self._spinbox, QDoubleSpinBox):
            self._spinbox.setDecimals(decimals)

    def is_double_spinbox(self) -> bool:
        """Check if this is using a QDoubleSpinBox."""
        return isinstance(self._spinbox, QDoubleSpinBox)


class VSpinBox(QSpinBox):
    """A styled number input component - basic styling only."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self._apply_styles()

    def _apply_styles(self) -> None:
        """Apply consistent styling to the number input."""
        style = """
            QSpinBox {
                border: 2px solid #CCCCCC;
                border-radius: 4px;
                padding: 6px 8px;
                min-height: 20px;
                font-size: 11px;
            }
            QSpinBox:focus {
                border-color: #0078D4;
                outline: none;
            }
            QSpinBox:hover {
                border-color: #999999;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                border: none;
                width: 16px;
            }
            QSpinBox::up-arrow, QSpinBox::down-arrow {
                width: 8px;
                height: 8px;
            }
        """
        self.setStyleSheet(style)


class VDoubleSpinBox(QDoubleSpinBox):
    """A styled decimal input component - basic styling only."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self._apply_styles()

    def _apply_styles(self) -> None:
        """Apply consistent styling to the decimal input."""
        style = """
            QDoubleSpinBox {
                border: 2px solid #CCCCCC;
                border-radius: 4px;
                padding: 6px 8px;
                min-height: 20px;
                font-size: 11px;
            }
            QDoubleSpinBox:focus {
                border-color: #0078D4;
                outline: none;
            }
            QDoubleSpinBox:hover {
                border-color: #999999;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                border: none;
                width: 16px;
            }
            QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {
                width: 8px;
                height: 8px;
            }
        """
        self.setStyleSheet(style)
