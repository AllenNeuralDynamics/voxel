"""Separator display component."""

from typing import Literal

from PySide6.QtWidgets import QFrame, QWidget

from exaspim.ui.theme import Colors


class Separator(QFrame):
    """Horizontal or vertical separator line.

    Usage:
        # Horizontal separator (default)
        hsep = Separator()

        # Vertical separator
        vsep = Separator(orientation="vertical")

        # Custom color
        sep = Separator(color=Colors.ACCENT)
    """

    def __init__(
        self,
        orientation: Literal["horizontal", "vertical"] = "horizontal",
        color: str = Colors.BORDER,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._orientation = orientation
        self._color = color
        self._apply_style()

    def _apply_style(self) -> None:
        """Apply the separator styling based on orientation."""
        if self._orientation == "horizontal":
            self.setFrameShape(QFrame.Shape.HLine)
            self.setFixedHeight(1)
        else:
            self.setFrameShape(QFrame.Shape.VLine)
            self.setFixedWidth(1)

        self.setStyleSheet(f"background-color: {self._color};")
