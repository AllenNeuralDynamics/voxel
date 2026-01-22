"""Dark card container component with rounded borders."""

from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget
from voxel_qt.ui.theme import BorderRadius, Colors, Spacing


class CardDark(QWidget):
    """A container with rounded borders and customizable styling.

    Use CardDark for grouping related content with a distinct visual boundary.
    Unlike Card, CardDark has no title and is purely a visual container.

    Usage:
        card = CardDark()
        card.layout().addWidget(some_widget)

        # Or with custom styling
        card = CardDark(
            color=Colors.BG_MEDIUM,
            border_color=Colors.BORDER,
            border_radius=BorderRadius.LG,
        )
    """

    def __init__(
        self,
        color: str = Colors.BG_MEDIUM,
        border_color: str = Colors.BORDER,
        border_radius: int = BorderRadius.LG,
        border_width: int = 1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._color = color
        self._border_color = border_color
        self._border_radius = border_radius
        self._border_width = border_width

        # Default layout with standard padding
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        brush = QBrush(QColor(self._color))
        pen = QPen(QColor(self._border_color))
        pen.setWidth(self._border_width)

        painter.setBrush(brush)
        painter.setPen(pen)

        # Adjust rect to account for pen width
        adj = self._border_width // 2 + 1
        rect = self.rect().adjusted(adj, adj, -adj, -adj)
        painter.drawRoundedRect(rect, self._border_radius, self._border_radius)

        if event is not None:
            super().paintEvent(event)

    def setColor(self, color: str) -> None:
        """Set the background color."""
        self._color = color
        self.update()

    def setBorderColor(self, color: str) -> None:
        """Set the border color."""
        self._border_color = color
        self.update()

    def setBorderRadius(self, radius: int) -> None:
        """Set the border radius."""
        self._border_radius = radius
        self.update()

    def updateVisualStyle(
        self,
        color: str | None = None,
        border_color: str | None = None,
        border_radius: int | None = None,
    ) -> None:
        """Set multiple visual style properties at once."""
        if color is not None:
            self._color = color
        if border_color is not None:
            self._border_color = border_color
        if border_radius is not None:
            self._border_radius = border_radius
        self.update()
