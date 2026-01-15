"""Animated toggle switch component."""

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Slot,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QCheckBox, QSizePolicy, QVBoxLayout, QWidget


class _AnimatedToggle(QCheckBox):
    """An animated toggle switch component.

    Features:
    - Smooth sliding animation with customizable easing
    - Customizable colors for different states
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

        self.setContentsMargins(8, 0, 8, 0)
        self._handle_position = 0.0

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(self.sizeHint())

        # Setup slide animation
        self.animation = QPropertyAnimation(self, b"handle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(200)

        self.stateChanged.connect(self._setup_animation)

    def sizeHint(self) -> QSize:
        return QSize(58, 45)

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
        handle_radius = round(0.24 * cont_rect.height())

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(self._transparent_pen)
        bar_rect = QRectF(0, 0, cont_rect.width() - handle_radius, 0.40 * cont_rect.height())
        bar_rect.moveCenter(QPointF(cont_rect.center()))
        rounding = bar_rect.height() / 2

        trail_length = cont_rect.width() - 2 * handle_radius
        x_pos = cont_rect.x() + handle_radius + trail_length * self._handle_position

        if self.isChecked():
            p.setBrush(self._bar_checked_brush)
            p.drawRoundedRect(bar_rect, rounding, rounding)
            p.setBrush(self._handle_checked_brush)
        else:
            p.setBrush(self._bar_brush)
            p.drawRoundedRect(bar_rect, rounding, rounding)
            p.setPen(self._light_grey_pen)
            p.setBrush(self._handle_brush)

        p.drawEllipse(QPointF(x_pos, bar_rect.center().y()), handle_radius, handle_radius)
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
