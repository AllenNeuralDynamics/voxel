"""Animated toggle switch component with soft-minimal design."""

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Slot,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QCheckBox, QSizePolicy, QVBoxLayout, QWidget

from spim_qt.ui.theme import BorderRadius


class _AnimatedToggle(QCheckBox):
    """An animated toggle switch component with soft-minimal design.

    Features:
    - Smooth sliding animation with customizable easing
    - Customizable colors for different states
    - Compact size with subtle rounded corners (2px radius)
    - Drop-in replacement for QCheckBox
    """

    _transparent_pen = QPen(Qt.GlobalColor.transparent)
    _light_grey_pen = QPen(Qt.GlobalColor.lightGray)

    def __init__(
        self,
        parent: QWidget | None = None,
        bar_color: Qt.GlobalColor | str = Qt.GlobalColor.gray,
        checked_color: str = "#0078D4",  # Microsoft blue
        handle_color: Qt.GlobalColor = Qt.GlobalColor.white,
    ):
        super().__init__(parent)

        self._bar_brush = QBrush(bar_color)
        self._bar_checked_brush = QBrush(QColor(checked_color).lighter())

        self._handle_brush = QBrush(handle_color)
        self._handle_checked_brush = QBrush(QColor(checked_color))

        self.setContentsMargins(2, 0, 2, 0)
        self._handle_position = 0.0

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(self.sizeHint())

        # Setup slide animation
        self.animation = QPropertyAnimation(self, b"handle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(150)

        self.stateChanged.connect(self._setup_animation)

    def sizeHint(self) -> QSize:
        return QSize(36, 20)

    def hitButton(self, pos: QPoint) -> bool:
        return self.contentsRect().contains(pos)

    @Slot(int)
    def _setup_animation(self, value: int) -> None:
        self.animation.stop()
        if value:
            self.animation.setEndValue(1.0)
        else:
            self.animation.setEndValue(0.0)
        self.animation.start()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        if event is None:
            return
        cont_rect = self.contentsRect()
        radius = BorderRadius.SM

        # Track dimensions - fill most of content rect
        track_height = cont_rect.height() - 4
        track_rect = QRectF(
            cont_rect.x() + 1,
            cont_rect.y() + 2,
            cont_rect.width() - 2,
            track_height,
        )

        # Handle dimensions - slightly smaller than track height
        handle_size = track_height - 4
        handle_margin = 2

        # Handle position (left when off, right when on)
        trail_length = track_rect.width() - handle_size - (handle_margin * 2)
        x_pos = track_rect.x() + handle_margin + trail_length * self._handle_position
        y_pos = track_rect.y() + (track_height - handle_size) / 2

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(self._transparent_pen)

        # Draw track
        if self.isChecked():
            p.setBrush(self._bar_checked_brush)
        else:
            p.setBrush(self._bar_brush)
        p.drawRoundedRect(track_rect, radius, radius)

        # Draw handle
        handle_rect = QRectF(x_pos, y_pos, handle_size, handle_size)
        if self.isChecked():
            p.setBrush(self._handle_checked_brush)
        else:
            p.setPen(self._light_grey_pen)
            p.setBrush(self._handle_brush)
        p.drawRoundedRect(handle_rect, radius, radius)

        p.end()

    def _get_handle_position(self) -> float:
        return self._handle_position

    def _set_handle_position(self, pos: float) -> None:
        self._handle_position = pos
        self.update()

    handle_position = Property(float, _get_handle_position, _set_handle_position)


class Toggle(QWidget):
    """A wrapper widget for the animated toggle component.

    Exposes the toggled signal directly for signal-based architecture.

    Usage:
        toggle = Toggle()
        toggle.toggled.connect(self._on_enabled_changed)
        toggle.setChecked(True)
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        bar_color: Qt.GlobalColor | str = Qt.GlobalColor.gray,
        checked_color: str = "#0078D4",
        handle_color: Qt.GlobalColor = Qt.GlobalColor.white,
    ):
        super().__init__(parent=parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._toggle = _AnimatedToggle(
            bar_color=bar_color,
            checked_color=checked_color,
            handle_color=handle_color,
        )

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(self._toggle.sizeHint())

        layout.addWidget(self._toggle)

    def isChecked(self) -> bool:
        return self._toggle.isChecked()

    def setChecked(self, checked: bool) -> None:
        self._toggle.setChecked(checked)

    def sizeHint(self) -> QSize:
        return self._toggle.sizeHint()

    @property
    def toggled(self):
        """The toggled signal - emits bool when state changes."""
        return self._toggle.toggled
