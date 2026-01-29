"""Sliders with 3-layer visualization: actual, target, input."""

from PySide6.QtCore import QRectF, Qt, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QWidget

from voxel_qt.ui.kit.button import ToolButton
from voxel_qt.ui.kit.input.spinbox import DoubleSpinBox
from voxel_qt.ui.kit.theme import Colors, ControlSize, Spacing


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

        # Input line dimensions
        input_line_width = 1
        input_line_height = 12
        input_line_y = (h - input_line_height) // 2

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

        # 4. Draw input handle (only when unlocked and not overlapping target)
        if not self._locked and abs(self._input - self._target) > 0.01:
            # Center the input line within the same coordinate space as target handle
            input_x = self._input * (w - handle_width) + (handle_width - input_line_width) / 2
            # Draw dark outline first (wider and taller)
            outline_rect = QRectF(input_x - 1, input_line_y - 1, input_line_width + 2, input_line_height + 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#000000")))
            painter.drawRoundedRect(outline_rect, 1, 1)
            # Draw white line on top (thinner and shorter)
            input_rect = QRectF(input_x, input_line_y, input_line_width, input_line_height)
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


class Slider(QWidget):
    """3-layer value track: actual (progress) -> target (indicator) -> input (command).

    Visual layers (bottom to top):
    - Progress bar: shows actual value (colored fill)
    - Target indicator: shows target value (colored handle, always visible)
    - Input slider: shows pending command (thin white handle, visible when unlocked)

    Lock state can be controlled programmatically but there is no UI for it.
    For a user-controllable lock button, use LockableSlider.

    Usage:
        slider = Slider(min_value=0, max_value=100, color="#0078d4")
        slider.inputReleased.connect(on_user_input)

        # Update from device properties:
        slider.setActual(current_value)
        slider.setTarget(target_value)
    """

    inputReleased = Signal(float)  # Emitted when user releases input slider (real value)
    lockedChanged = Signal(bool)  # Emitted when lock state changes

    def __init__(
        self,
        min_value: float = 0.0,
        max_value: float = 100.0,
        color: str = "#0078d4",
        locked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min = min_value
        self._max = max_value
        self._color = QColor(color)
        self._locked = locked

        # Values (normalized 0-1)
        self._actual = 0.0
        self._target = 0.0
        self._input = 0.0

        # Create track
        self._track = _SliderTrack(self)

        self._configure_layout()
        self._configure_widgets()
        self._connect_signals()

    def _configure_layout(self) -> None:
        """Arrange widgets into layouts."""
        self.setMinimumHeight(28)
        self.setMinimumWidth(100)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._track, stretch=1)

    def _configure_widgets(self) -> None:
        """Configure widget properties and initial state."""
        self._track.set_state(
            actual=self._actual,
            target=self._target,
            input_ratio=self._input,
            locked=self._locked,
            color=self._color,
        )

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        self._track.inputReleased.connect(self._on_track_input_released)

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

    @property
    def locked(self) -> bool:
        """Get locked state."""
        return self._locked

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
        if self._locked == locked:
            return
        self._locked = locked
        if locked:
            # Sync input to target when locking
            self._input = self._target
        self._track.set_state(locked=self._locked, input_ratio=self._input)
        self.lockedChanged.emit(locked)

    @Slot(float, float)
    def setRange(self, min_value: float, max_value: float) -> None:
        """Update the value range."""
        self._min = min_value
        self._max = max_value

    @Slot(str)
    def setColor(self, color: str) -> None:
        """Update the accent color."""
        self._color = QColor(color)
        self._track.set_state(color=self._color)


class LockButton(ToolButton):
    """Toggle button for lock/unlock state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            ("mdi6.lock", "mdi6.lock-off-outline"),
            checkable=True,
            size=ControlSize.MD,
            color=Colors.TEXT_MUTED,
            color_hover=Colors.TEXT,
            parent=parent,
        )
        self.setToolTip("Click to unlock slider for manual input")

    @property
    def locked(self) -> bool:
        """Get locked state. Checked = unlocked."""
        return not self.isChecked()

    def setLocked(self, locked: bool) -> None:
        """Set locked state without emitting toggled signal."""
        self.blockSignals(True)
        self.setChecked(not locked)
        self.blockSignals(False)
        self._update_icon(not locked)


class LockableSlider(Slider):
    """Slider with a user-controllable lock button.

    Extends Slider with a lock/unlock button that allows the user to toggle
    between locked mode (input follows target) and unlocked mode (user can
    drag the input handle).

    Usage:
        slider = LockableSlider(min_value=0, max_value=100, color="#0078d4")
        slider.inputReleased.connect(on_user_input)

        # Update from device properties:
        slider.setActual(current_value)
        slider.setTarget(target_value)
    """

    def __init__(
        self,
        min_value: float = 0.0,
        max_value: float = 100.0,
        color: str = "#0078d4",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(min_value, max_value, color, locked=True, parent=parent)

        self._lock_btn = LockButton()
        self._lock_btn.toggled.connect(self._on_lock_toggled)

        layout = self.layout()
        if layout is not None:
            layout.setSpacing(4)
            layout.addWidget(self._lock_btn)

    def _on_lock_toggled(self, checked: bool) -> None:
        """Handle lock button toggle. Checked = unlocked."""
        self.setLocked(not checked)

    @Slot(bool)
    def setLocked(self, locked: bool) -> None:
        """Set locked state programmatically."""
        super().setLocked(locked)
        self._lock_btn.setLocked(locked)


class SliderSpinBox(QWidget):
    """Slider + SpinBox + optional LockButton for numeric input.

    Combines a 3-layer slider (actual/target/input) with a spinbox for precise
    numeric entry. Optionally includes a lock button for locking the slider.

    Usage:
        # Basic (no lock button)
        slider = SliderSpinBox(min_value=0, max_value=100)
        slider.valueChanged.connect(on_value_changed)

        # With lock button
        slider = SliderSpinBox(min_value=0, max_value=100, show_lock=True)

        # Update from device
        slider.setActual(current_value)
        slider.setTarget(target_value)
    """

    valueChanged = Signal(float)  # Emitted when user changes value (spinbox or slider)

    def __init__(
        self,
        min_value: float = 0.0,
        max_value: float = 100.0,
        value: float = 0.0,
        *,
        decimals: int = 2,
        step: float = 0.1,
        show_lock: bool = False,
        color: str = Colors.ACCENT,
        size: ControlSize = ControlSize.SM,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._show_lock = show_lock

        # Create widgets
        self._spinbox = DoubleSpinBox(
            value=value,
            min_val=min_value,
            max_val=max_value,
            decimals=decimals,
            step=step,
            size=size,
        )
        self._slider = Slider(
            min_value=min_value,
            max_value=max_value,
            color=color,
            locked=show_lock,  # Start locked if lock button is shown
        )
        self._lock_btn: LockButton | None = None
        if show_lock:
            self._lock_btn = LockButton()

        self._configure_layout()
        self._connect_signals()

        # Set initial value
        if value:
            self._slider.setTarget(value)
            self._slider.setActual(value)

    def _configure_layout(self) -> None:
        """Arrange widgets."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        layout.addWidget(self._spinbox)
        layout.addWidget(self._slider, stretch=1)
        if self._lock_btn:
            layout.addWidget(self._lock_btn)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._spinbox.valueChanged.connect(self._on_spinbox_changed)
        self._slider.inputReleased.connect(self._on_slider_changed)
        if self._lock_btn:
            self._lock_btn.toggled.connect(self._on_lock_toggled)

    def _on_spinbox_changed(self, value: float) -> None:
        """Handle spinbox value change."""
        self._slider.setTarget(value)
        self.valueChanged.emit(value)

    def _on_slider_changed(self, value: float) -> None:
        """Handle slider input release."""
        self._spinbox.blockSignals(True)
        self._spinbox.setValue(value)
        self._spinbox.blockSignals(False)
        self.valueChanged.emit(value)

    def _on_lock_toggled(self, checked: bool) -> None:
        """Handle lock button toggle. Checked = unlocked."""
        self._slider.setLocked(not checked)

    # === Public API ===

    def setActual(self, value: float) -> None:
        """Update the actual value (progress bar)."""
        self._slider.setActual(value)

    def setTarget(self, value: float) -> None:
        """Update the target value (handle) and spinbox."""
        self._slider.setTarget(value)
        self._spinbox.blockSignals(True)
        self._spinbox.setValue(value)
        self._spinbox.blockSignals(False)

    def setRange(self, min_value: float, max_value: float) -> None:
        """Update the value range."""
        self._slider.setRange(min_value, max_value)
        self._spinbox.setRange(min_value, max_value)

    def setLocked(self, locked: bool) -> None:
        """Set locked state programmatically."""
        self._slider.setLocked(locked)
        if self._lock_btn:
            self._lock_btn.setLocked(locked)

    @property
    def locked(self) -> bool:
        """Get locked state."""
        return self._slider.locked

    def value(self) -> float:
        """Get current spinbox value."""
        return self._spinbox.value()
