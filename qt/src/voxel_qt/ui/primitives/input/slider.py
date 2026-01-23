"""Lockable slider with 3-layer visualization: actual, target, input."""

from PySide6.QtCore import QRectF, Qt, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QWidget

from voxel_qt.ui.theme import Colors


class _SliderTrack(QWidget):
    """Custom painted slider track with 3 layers.

    A dumb renderer that only paints state passed to it via set_state().
    Emits signals for user input - no back-reference to parent.
    """

    inputChanged = Signal(float)  # Emitted during drag (ratio 0-1)
    inputReleased = Signal(float)  # Emitted on mouse release (ratio 0-1)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Display state (set by parent via set_state)
        self._color = QColor("#0078d4")
        self._actual = 0.0
        self._target = 0.0
        self._input = 0.0
        self._locked = True

        # Interaction state (internal)
        self._dragging = False

    def set_state(
        self,
        *,
        actual: float | None = None,
        target: float | None = None,
        input_ratio: float | None = None,
        locked: bool | None = None,
        color: QColor | None = None,
    ) -> None:
        """Update display state. Only provided values are changed."""
        if actual is not None:
            self._actual = actual
        if target is not None:
            self._target = target
        if input_ratio is not None:
            self._input = input_ratio
        if locked is not None:
            self._locked = locked
        if color is not None:
            self._color = color
        self.update()

    def paintEvent(self, _event) -> None:
        """Paint the 3-layer slider."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Track dimensions
        track_height = 8
        track_y = (h - track_height) // 2
        track_rect = QRectF(0, track_y, w, track_height)

        # Handle dimensions
        handle_width = 6
        handle_height = 16
        handle_y = (h - handle_height) // 2

        # Colors
        bg_color = QColor(Colors.BG_LIGHT)
        border_color = QColor(Colors.BORDER)
        input_color = QColor(Colors.TEXT_BRIGHT)

        # 1. Draw track background
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(track_rect, 4, 4)

        # 2. Draw actual value (progress fill)
        if self._actual > 0:
            fill_width = max(0, self._actual * w - 2)  # -2 for border inset
            if fill_width > 0:
                fill_rect = QRectF(1, track_y + 1, fill_width, track_height - 2)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(self._color))
                painter.drawRoundedRect(fill_rect, 3, 3)

        # 3. Draw target handle (colored, always visible)
        target_x = self._target * (w - handle_width)
        target_rect = QRectF(target_x, handle_y, handle_width, handle_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._color))
        painter.drawRoundedRect(target_rect, 3, 3)

        # 4. Draw input handle (white, only when unlocked)
        if not self._locked:
            input_x = self._input * (w - 2)  # Thin handle
            input_rect = QRectF(input_x, handle_y, 2, handle_height)
            painter.setBrush(QBrush(input_color))
            painter.drawRoundedRect(input_rect, 1, 1)

        painter.end()

    def mousePressEvent(self, event) -> None:
        """Start dragging if unlocked."""
        if not self._locked and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._update_input_from_mouse(event.position().x())

    def mouseMoveEvent(self, event) -> None:
        """Update input while dragging."""
        if self._dragging:
            self._update_input_from_mouse(event.position().x())

    def mouseReleaseEvent(self, event) -> None:
        """Emit signal on release."""
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.inputReleased.emit(self._input)

    def _update_input_from_mouse(self, x: float) -> None:
        """Update input value from mouse position."""
        ratio = max(0.0, min(1.0, x / self.width()))
        self._input = ratio
        self.update()
        self.inputChanged.emit(ratio)


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

    inputReleased = Signal(float)  # Emitted when user releases input slider (real value)

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
        self._color = QColor(color)
        self._locked = True

        # Values (normalized 0-1)
        self._actual = 0.0
        self._target = 0.0
        self._input = 0.0

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget layout."""
        self.setMinimumHeight(28)
        self.setMinimumWidth(100)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Track area (custom painted, no back-reference)
        self._track = _SliderTrack(self)
        self._track.set_state(
            actual=self._actual,
            target=self._target,
            input_ratio=self._input,
            locked=self._locked,
            color=self._color,
        )
        self._track.inputReleased.connect(self._on_track_input_released)
        layout.addWidget(self._track, stretch=1)

        # Lock checkbox
        self._checkbox = QCheckBox()
        self._checkbox.setChecked(False)  # Unchecked = locked
        self._checkbox.setToolTip("Check to unlock slider for manual input")
        self._checkbox.toggled.connect(self._on_checkbox_toggled)
        self._update_checkbox_style()
        layout.addWidget(self._checkbox)

    def _update_checkbox_style(self) -> None:
        """Update checkbox styling with current color."""
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
                background-color: {self._color.name()};
                border: 1px solid {self._color.name()};
                border-radius: 2px;
            }}
        """)

    def _on_checkbox_toggled(self, checked: bool) -> None:
        """Handle lock checkbox toggle. Checked = unlocked."""
        self._locked = not checked
        if not checked:
            # Lock: sync input to target
            self._input = self._target
        self._track.set_state(locked=self._locked, input_ratio=self._input)

    def _on_track_input_released(self, ratio: float) -> None:
        """Handle input release from track."""
        self._input = ratio
        value = self._ratio_to_value(ratio)
        self.inputReleased.emit(value)

    def _value_to_ratio(self, value: float) -> float:
        """Convert real value to 0-1 ratio."""
        if self._max == self._min:
            return 0.0
        return (value - self._min) / (self._max - self._min)

    def _ratio_to_value(self, ratio: float) -> float:
        """Convert 0-1 ratio to real value."""
        return self._min + ratio * (self._max - self._min)

    # === Public Slots ===

    @Slot(float)
    def setActual(self, value: float) -> None:
        """Update the actual value (progress bar)."""
        self._actual = self._value_to_ratio(value)
        self._track.set_state(actual=self._actual)

    @Slot(float)
    def setTarget(self, value: float) -> None:
        """Update the target value (colored indicator)."""
        self._target = self._value_to_ratio(value)
        if self._locked:
            self._input = self._target
            self._track.set_state(target=self._target, input_ratio=self._input)
        else:
            self._track.set_state(target=self._target)

    @Slot(float)
    def setInput(self, value: float) -> None:
        """Update the input value (command slider)."""
        self._input = self._value_to_ratio(value)
        self._track.set_state(input_ratio=self._input)

    @Slot(bool)
    def setLocked(self, locked: bool) -> None:
        """Set locked state programmatically."""
        self._checkbox.setChecked(not locked)

    @Slot(float, float)
    def setRange(self, min_value: float, max_value: float) -> None:
        """Update the value range."""
        self._min = min_value
        self._max = max_value

    @Slot(str)
    def setColor(self, color: str) -> None:
        """Update the accent color."""
        self._color = QColor(color)
        self._update_checkbox_style()
        self._track.set_state(color=self._color)
