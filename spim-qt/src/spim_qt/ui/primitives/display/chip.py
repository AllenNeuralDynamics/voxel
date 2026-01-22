"""Chip component for displaying colored labels."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from spim_qt.ui.theme import BorderRadius, Spacing


def _get_text_color(bg_color: str) -> str:
    """Determine if text should be black or white based on background brightness."""
    bg_color = bg_color.lstrip("#")
    r, g, b = tuple(int(bg_color[i : i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.55 else "#FFFFFF"


class Chip(QWidget):
    """A colored chip/badge for displaying short text with visual emphasis.

    Automatically calculates text color (black/white) based on background
    brightness for optimal contrast.

    Usage:
        chip = Chip("560 nm", color="#BEF264")
        chip = Chip("488 nm", color="#67e8f9", border_color="#0E7490")
    """

    def __init__(
        self,
        text: str,
        color: str = "#e0e0e0",
        border_color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self._label = QLabel(text)
        self._color = color
        self._border_color = border_color

        self._update_text_color()

        layout = QHBoxLayout()
        layout.addWidget(self._label)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        self.setLayout(layout)

    def _update_text_color(self) -> None:
        text_color = _get_text_color(self._color)
        self._label.setStyleSheet(f"color: {text_color};")

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        brush = QBrush(QColor(self._color))

        if self._border_color:
            pen = QPen(QColor(self._border_color))
            pen.setWidth(2)
        else:
            pen = QPen(Qt.PenStyle.NoPen)

        painter.setBrush(brush)
        painter.setPen(pen)
        radius = BorderRadius.LG
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), radius, radius)

        if event is not None:
            super().paintEvent(event)

    def setText(self, text: str) -> None:
        self._label.setText(text)

    def text(self) -> str:
        return self._label.text()

    def getColor(self) -> str:
        return self._color

    def setColor(self, color: str, border_color: str | None = None) -> None:
        self._color = color
        self._border_color = border_color
        self._update_text_color()
        self.update()
