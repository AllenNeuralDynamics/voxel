from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget


def get_text_color(bg_color: str) -> str:
    """Determines if text should be black or white based on background color brightness."""
    # Convert hex to RGB
    bg_color = bg_color.lstrip("#")
    r, g, b = tuple(int(bg_color[i : i + 2], 16) for i in (0, 2, 4))
    # Calculate luminance
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.55 else "#FFFFFF"


class Chip(QWidget):
    """A simple chip widget for displaying information."""

    def __init__(
        self, text: str, color: str = "#e0e0e0", border_color: str | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)

        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.label = QLabel(text)
        self._color = color
        self._border_color = border_color

        self._update_text_color()

        layout = QHBoxLayout()
        layout.addWidget(self.label)
        layout.setContentsMargins(8, 4, 8, 4)  # left, top, right, bottom
        self.setLayout(layout)

    def _update_text_color(self):
        text_color = get_text_color(self._color)
        self.label.setStyleSheet(f"color: {text_color};")

    def paintEvent(self, event: QPaintEvent):
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

        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)

        super().paintEvent(event)

    def setText(self, text: str):
        self.label.setText(text)

    def text(self) -> str:
        return self.label.text()

    def color(self) -> str:
        return self._color

    def setColor(self, color: str, border_color: str | None = None):
        self._color = color
        self._border_color = border_color
        self._update_text_color()
        self.update()


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication()
    window = QMainWindow()

    container = QWidget()
    layout = QHBoxLayout(container)

    chip1 = Chip("560 nm", color="#BEF264", border_color="#4D7C0F")
    chip2 = Chip("488 nm", color="#67e8f9", border_color="#0E7490")

    layout.addWidget(chip1)
    layout.addWidget(chip2)

    window.setCentralWidget(container)
    window.show()
    app.exec()
