from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from spim_widgets.laser.utils import lighten_hex_color, rgb_to_css_string, wavelength_to_rgb
from spim_widgets.ui.input.binding import FieldBinder


class VSpinBox(QWidget):
    valueChanged = Signal(float)  # noqa: N815
    HEIGHT = 30

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._value = 0.0
        self._minimum = 0.0
        self._maximum = 100.0
        self._single_step = 0.1
        self._decimals = 1

        self._minus_button = QPushButton("-")
        self._plus_button = QPushButton("+")
        self._line_edit = QLineEdit(str(self._value))
        self._line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Set fixed height for all components
        self._minus_button.setFixedHeight(self.HEIGHT)
        self._plus_button.setFixedHeight(self.HEIGHT)
        self._line_edit.setFixedHeight(self.HEIGHT)

        # Validator
        self._validator = QDoubleValidator()
        self._line_edit.setValidator(self._validator)

        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._minus_button)
        layout.addWidget(self._line_edit)
        layout.addWidget(self._plus_button)

        # Connections
        self._minus_button.clicked.connect(self._decrement)
        self._plus_button.clicked.connect(self._increment)
        self._line_edit.editingFinished.connect(self._on_editing_finished)

        # Styling
        self._minus_button.setObjectName("minusButton")
        self._plus_button.setObjectName("plusButton")
        self._line_edit.setObjectName("lineEdit")

        # Initialize colors
        self._bg_color = "#18181b"
        self._border_color = "#3e3e44"
        self._text_color = "#f4f4f5"
        self.setColor()  # Apply initial default style

    def _increment(self):
        self.setValue(self._value + self._single_step)

    def _decrement(self):
        self.setValue(self._value - self._single_step)

    def _on_editing_finished(self):
        try:
            val = float(self._line_edit.text())
            self.setValue(val)
        except ValueError:
            self._line_edit.setText(f"{self._value:.{self._decimals}f}")

    def value(self) -> float:
        return self._value

    def setValue(self, value: float):
        clamped_value = max(self._minimum, min(value, self._maximum))
        # Check if value actually changed before updating
        value_changed = self._value != clamped_value
        # Always update internal state and display
        self._value = clamped_value
        self._line_edit.setText(f"{self._value:.{self._decimals}f}")
        # Emit signal if value changed
        if value_changed:
            self.valueChanged.emit(self._value)

    def minimum(self) -> float:
        return self._minimum

    def setMinimum(self, value: float):
        self._minimum = value
        self._validator.setBottom(value)

    def maximum(self) -> float:
        return self._maximum

    def setMaximum(self, value: float):
        self._maximum = value
        self._validator.setTop(value)

    def singleStep(self) -> float:
        return self._single_step

    def setSingleStep(self, value: float):
        self._single_step = value

    def setSuffix(self, suffix: str):
        pass

    def setKeyboardTracking(self, tracking: bool):
        pass

    def setDecimals(self, decimals: int):
        self._decimals = decimals
        self._validator.setDecimals(decimals)
        # Update display with new decimal precision
        self._line_edit.setText(f"{self._value:.{self._decimals}f}")

    def setColor(self, background: str | None = None, border: str | None = None, text: str | None = None):
        if background:
            self._bg_color = background
        if border:
            self._border_color = border
        if text:
            self._text_color = text

        hover_bg_color = lighten_hex_color(self._bg_color, factor=0.1)

        self.setStyleSheet(f"""
            #minusButton, #plusButton {{
                border: 1px solid {self._border_color};
                background-color: {self._bg_color};
                color: {self._text_color};
                min-width: 30px;
            }}
            #minusButton {{
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
                border-right: none;
            }}
            #plusButton {{
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                border-left: none;
            }}
            #lineEdit {{
                border: 1px solid {self._border_color};
                border-left: none;
                border-right: none;
                padding: 4px;
                background-color: {self._bg_color};
                color: {self._text_color};
            }}
            #minusButton:hover, #plusButton:hover {{
                background-color: {hover_bg_color};
            }}
        """)


class PowerSetpointInput(QWidget):
    def __init__(
        self,
        binding: FieldBinder[float, float],
        wavelength: int | None = None,
        min_value: float = 0.0,
        max_value: float = 1000.0,
        step: float = 1.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._binding = binding
        self._min_value = min_value
        self._max_value = max_value
        self._step = step

        self._title = QLabel("Power Setpoint (mW)")
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self._slider.setTickInterval(int((max_value - min_value) / 10) or 10)
        self._spin = VSpinBox()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._title)
        lay.addWidget(self._slider)
        lay.addWidget(self._spin)

        # Configure ranges
        self._slider.setMinimum(int(min_value))
        self._slider.setMaximum(int(max_value))
        self._slider.setSingleStep(int(step))

        self._spin.setMinimum(min_value)
        self._spin.setMaximum(max_value)
        self._spin.setSingleStep(step)
        self._spin.setDecimals(0)  # Show whole numbers for power

        # Device → UI
        self._binding.value_changed.connect(self._render_value)

        # UI → Device
        self._slider.setTracking(True)
        self._slider.valueChanged.connect(lambda i: self._binding.set_value(float(i)))
        self._spin.valueChanged.connect(lambda: self._binding.set_value(self._spin.value()))

        # Initial value
        if (val := self._binding.get_value()) is not None:
            self._render_value(val)

        if wavelength is not None:
            self._apply_wavelength_style(wavelength)

    def _render_value(self, value: float) -> None:
        """Update UI widgets with new value from device.

        QSignalBlocker prevents the widgets from emitting signals back to the binder,
        which would cause an infinite loop.
        """
        with QSignalBlocker(self._slider), QSignalBlocker(self._spin):
            self._slider.setValue(int(value))
            self._spin.setValue(value)

    def update_range(self, min_value: float, max_value: float, step: float) -> None:
        """Update the min/max/step ranges from property metadata."""
        self._min_value = min_value
        self._max_value = max_value
        self._step = step

        with QSignalBlocker(self._slider), QSignalBlocker(self._spin):
            self._slider.setMinimum(int(min_value))
            self._slider.setMaximum(int(max_value))
            self._slider.setSingleStep(int(step))
            self._slider.setTickInterval(int((max_value - min_value) / 10) or 10)

            self._spin.setMinimum(min_value)
            self._spin.setMaximum(max_value)
            self._spin.setSingleStep(step)

    def _apply_wavelength_style(self, wavelength: int) -> None:
        palette = self.palette()
        r, g, b = wavelength_to_rgb(wavelength)
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 12px;
                background: {palette.color(palette.ColorRole.Base).name()};
                border-radius: 6px;
            }}
            QSlider::handle:horizontal {{
                background: {rgb_to_css_string((r, g, b))};
                border: 1px solid {rgb_to_css_string((r / 2, g / 2, b / 2))};
                width: 18px;
                margin: -4px 0;
                border-radius: 9px;
            }}
            QSlider::sub-page:horizontal {{
                background: {rgb_to_css_string((r * 0.8, g * 0.8, b * 0.8))};
                border-radius: 6px;
            }}
            QSlider::add-page:horizontal {{
                background: {palette.color(palette.ColorRole.AlternateBase).name()};
                border-radius: 6px;
            }}
        """)
        # color_str = rgb_to_css_string((r, g, b))
        # self._spin.setColor(border=color_str, text=color_str)
