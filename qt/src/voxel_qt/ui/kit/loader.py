"""Animated loader components."""

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from .theme import Colors


class LinearLoader(QWidget):
    """Animated horizontal line loader that moves back and forth."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        color: str = Colors.ACCENT,
        track_color: str = Colors.BG_DARK,
        height: int = 4,
        bar_width_ratio: float = 0.3,
    ) -> None:
        super().__init__(parent)

        self._color = QColor(color)
        self._track_color = QColor(track_color)
        self._height = height
        self._bar_width_ratio = bar_width_ratio
        self._position = 0.0

        self.setFixedHeight(height)

        # Animation
        self._animation = QPropertyAnimation(self, b"position")
        self._animation.setDuration(1200)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._animation.setLoopCount(-1)  # Infinite loop

    def start(self) -> None:
        """Start the animation."""
        self._animation.start()

    def stop(self) -> None:
        """Stop the animation."""
        self._animation.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.stop()

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = value
        self.update()

    position = Property(float, _get_position, _set_position)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        bar_width = int(width * self._bar_width_ratio)

        # Draw track
        painter.fillRect(0, 0, width, height, self._track_color)

        # Calculate bar position (ping-pong motion)
        # position goes 0->1, we want the bar to go left->right->left
        travel_distance = width - bar_width
        if self._position <= 0.5:
            # Moving right: 0->0.5 maps to 0->travel_distance
            bar_x = int(self._position * 2 * travel_distance)
        else:
            # Moving left: 0.5->1 maps to travel_distance->0
            bar_x = int((1 - self._position) * 2 * travel_distance)

        # Draw bar
        painter.fillRect(bar_x, 0, bar_width, height, self._color)

        painter.end()
