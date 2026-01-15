"""Lockable slider with 3-layer visualization: actual, target, input."""

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QProgressBar, QSlider, QWidget

from exaspim.ui.theme import Colors


class LockableSlider(QWidget):
    """3-layer value track: actual (progress) -> target (indicator) -> input (command).

    Visual layers (bottom to top):
    - Progress bar: shows actual value (colored fill)
    - Target indicator: shows target value (colored handle, always visible)
    - Input slider: shows pending command (thin white handle, visible when unlocked)

    When locked: input follows target automatically, input handle hidden.
    When unlocked: input is user-controllable, emits inputReleased on release.

    Usage:
        slider = LockableSlider(min_value=0, max_value=100, color="#0078d4")
        slider.inputReleased.connect(on_user_input)

        # Update from device properties:
        slider.setActual(current_value)
        slider.setTarget(target_value)
    """

    inputReleased = Signal(float)  # Emitted when user releases input slider

    def __init__(
        self,
        min_value: float = 0.0,
        max_value: float = 100.0,
        color: str = "#0078d4",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min = min_value
        self._max = max_value
        self._color = color
        self._scale = 1000  # Internal slider scale for precision
        self._locked = True  # Start locked

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the 3-layer track with lock checkbox."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Track container for layered widgets
        self._track = QWidget()
        self._track.setFixedHeight(24)
        layout.addWidget(self._track, stretch=1)

        # Layer 1: Progress bar (actual value)
        self._progress = QProgressBar(self._track)
        self._progress.setRange(0, self._scale)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Colors.BG_LIGHT};
                border: 1px solid {Colors.BORDER_FOCUS};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {self._color};
                border-radius: 3px;
            }}
        """)

        # Layer 2: Target indicator (colored handle, always visible)
        self._target_slider = QSlider(Qt.Orientation.Horizontal, self._track)
        self._target_slider.setRange(0, self._scale)
        self._target_slider.setValue(0)
        self._target_slider.setEnabled(False)  # Never interactive
        self._target_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: transparent;
                height: 8px;
            }}
            QSlider::handle:horizontal {{
                background: {self._color};
                border: none;
                width: 8px;
                height: 20px;
                margin: -6px 0;
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: transparent;
            }}
            QSlider::add-page:horizontal {{
                background: transparent;
            }}
        """)

        # Layer 3: Input slider (thin white handle when unlocked)
        self._input_slider = QSlider(Qt.Orientation.Horizontal, self._track)
        self._input_slider.setRange(0, self._scale)
        self._input_slider.setValue(0)
        self._input_slider.setEnabled(False)  # Start disabled (locked)
        self._update_input_style(enabled=False)

        # Lock checkbox
        self._checkbox = QCheckBox()
        self._checkbox.setChecked(False)  # Unchecked = locked
        self._checkbox.setToolTip("Check to unlock slider for manual input")
        self._checkbox.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {Colors.BORDER};
                border: 1px solid {Colors.BORDER_FOCUS};
                border-radius: 2px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {self._color};
                border: 1px solid {self._color};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self._checkbox)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._checkbox.toggled.connect(self._on_checkbox_toggled)
        self._input_slider.sliderReleased.connect(self._on_input_released)

    def _update_input_style(self, enabled: bool) -> None:
        """Update input slider style based on enabled state."""
        if enabled:
            # Visible thin white handle
            self._input_slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    background: transparent;
                    height: 8px;
                }
                QSlider::handle:horizontal {
                    background: #ffffff;
                    border: none;
                    width: 2px;
                    height: 22px;
                    margin: -7px 0;
                    border-radius: 1px;
                }
                QSlider::handle:horizontal:hover {
                    background: #ffffff;
                    width: 3px;
                }
                QSlider::sub-page:horizontal {
                    background: transparent;
                }
                QSlider::add-page:horizontal {
                    background: transparent;
                }
            """)
        else:
            # Hidden handle
            self._input_slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    background: transparent;
                }
                QSlider::handle:horizontal {
                    background: transparent;
                    width: 0px;
                    height: 0px;
                }
            """)

    def resizeEvent(self, event) -> None:
        """Position the 3 layers within the track container."""
        super().resizeEvent(event)
        if hasattr(self, "_track"):
            w = self._track.width()
            h = self._track.height()
            # Progress bar: centered vertically, 8px height
            self._progress.setGeometry(0, (h - 8) // 2, w, 8)
            # Target and input sliders: full track area
            self._target_slider.setGeometry(0, 0, w, h)
            self._input_slider.setGeometry(0, 0, w, h)

    def _value_to_slider(self, value: float) -> int:
        """Convert real value to slider position."""
        if self._max == self._min:
            return 0
        ratio = (value - self._min) / (self._max - self._min)
        return int(ratio * self._scale)

    def _slider_to_value(self, slider_val: int) -> float:
        """Convert slider position to real value."""
        ratio = slider_val / self._scale
        return self._min + ratio * (self._max - self._min)

    def _on_checkbox_toggled(self, checked: bool) -> None:
        """Handle lock checkbox toggle. Checked = unlocked."""
        self._locked = not checked
        if checked:
            # Unlock: enable input slider
            self._input_slider.setEnabled(True)
            self._update_input_style(enabled=True)
        else:
            # Lock: disable and sync input to target
            self._input_slider.setEnabled(False)
            self._update_input_style(enabled=False)
            self._input_slider.setValue(self._target_slider.value())

    def _on_input_released(self) -> None:
        """Emit signal when user releases input slider."""
        if not self._locked:
            value = self._slider_to_value(self._input_slider.value())
            self.inputReleased.emit(value)

    # === Public Slots ===

    @Slot(float)
    def setActual(self, value: float) -> None:
        """Update the actual value (progress bar)."""
        self._progress.setValue(self._value_to_slider(value))

    @Slot(float)
    def setTarget(self, value: float) -> None:
        """Update the target value (colored indicator)."""
        slider_val = self._value_to_slider(value)
        self._target_slider.setValue(slider_val)
        # If locked, input follows target
        if self._locked:
            self._input_slider.setValue(slider_val)

    @Slot(float)
    def setInput(self, value: float) -> None:
        """Update the input value (command slider)."""
        self._input_slider.setValue(self._value_to_slider(value))

    @Slot(bool)
    def setLocked(self, locked: bool) -> None:
        """Set locked state programmatically."""
        # Checkbox checked = unlocked, so invert
        self._checkbox.setChecked(not locked)

    @Slot(float, float)
    def setRange(self, min_value: float, max_value: float) -> None:
        """Update the value range."""
        self._min = min_value
        self._max = max_value

    @Slot(str)
    def setColor(self, color: str) -> None:
        """Update the color (requires re-applying styles)."""
        self._color = color
        # Re-apply progress bar style
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Colors.BG_LIGHT};
                border: 1px solid {Colors.BORDER_FOCUS};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {self._color};
                border-radius: 3px;
            }}
        """)
        # Re-apply target slider style
        self._target_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: transparent;
                height: 8px;
            }}
            QSlider::handle:horizontal {{
                background: {self._color};
                border: none;
                width: 8px;
                height: 20px;
                margin: -6px 0;
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: transparent;
            }}
            QSlider::add-page:horizontal {{
                background: transparent;
            }}
        """)
        # Re-apply checkbox style
        self._checkbox.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {Colors.BORDER};
                border: 1px solid {Colors.BORDER_FOCUS};
                border-radius: 2px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {self._color};
                border: 1px solid {self._color};
                border-radius: 2px;
            }}
        """)
