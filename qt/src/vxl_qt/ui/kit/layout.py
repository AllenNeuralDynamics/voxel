"""Layout utilities and divider components."""

from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from .theme import Colors

# -----------------------------------------------------------------------------
# Dividers
# -----------------------------------------------------------------------------


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
        self.setFrameShape(QFrame.Shape.NoFrame)
        if self._orientation == "horizontal":
            self.setFixedHeight(1)
            self.setStyleSheet(f"background-color: {self._color};")
        else:
            self.setFixedWidth(1)
            self.setStyleSheet(f"background-color: {self._color};")


class Splitter(QSplitter):
    """A styled splitter with consistent appearance.

    Usage:
        splitter = Splitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
    """

    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Horizontal, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self._apply_style()

    def _apply_style(self) -> None:
        """Apply consistent splitter styling based on orientation."""
        if self.orientation() == Qt.Orientation.Horizontal:
            self.setStyleSheet(f"""
                QSplitter::handle {{
                    background-color: {Colors.BORDER};
                    width: 1px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QSplitter::handle {{
                    background-color: {Colors.BORDER};
                    height: 1px;
                }}
            """)

    def setOrientation(self, orientation: Qt.Orientation) -> None:
        """Override to update style when orientation changes."""
        super().setOrientation(orientation)
        self._apply_style()


# -----------------------------------------------------------------------------
# Layout Helpers
# -----------------------------------------------------------------------------


def vbox(parent: QWidget, spacing: int = 0, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QVBoxLayout:
    """Create and configure a QVBoxLayout on parent widget.

    Use for root layout setup to eliminate boilerplate.

    Usage:
        layout = vbox(self, spacing=Spacing.MD)
        layout.addWidget(header)
        layout.addWidget(content)
    """
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def hbox(parent: QWidget, spacing: int = 0, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QHBoxLayout:
    """Create and configure a QHBoxLayout on parent widget.

    Use for root layout setup to eliminate boilerplate.

    Usage:
        layout = hbox(self, spacing=Spacing.SM, margins=(8, 0, 8, 0))
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(button)
    """
    layout = QHBoxLayout(parent)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout
