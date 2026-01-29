"""Grid panel for acquisition grid display."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from voxel_qt.store import PreviewStore
from voxel_qt.ui.kit import Colors, Text, vbox
from voxel_qt.ui.panels.preview import PreviewThumbnail


class GridPanel(QWidget):
    """Grid panel with preview thumbnail."""

    def __init__(self, store: PreviewStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {Colors.BG_DARK};")

        layout = vbox(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._thumbnail = PreviewThumbnail(store)
        layout.addWidget(self._thumbnail, alignment=Qt.AlignmentFlag.AlignCenter)


class GridTablePanel(QWidget):
    """Grid table panel for displaying acquisition grid data."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {Colors.BG_DARK};")

        layout = vbox(self)

        label = Text.muted("Grid Table", color=Colors.TEXT_DISABLED)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
