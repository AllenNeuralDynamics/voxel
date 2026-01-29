"""Panel components for the control page."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from voxel_qt.ui.kit import Colors, Text, vbox
from voxel_qt.ui.panels.controls import ControlPanel
from voxel_qt.ui.panels.grid import GridPanel, GridTablePanel
from voxel_qt.ui.panels.logs import LogPanel
from voxel_qt.ui.panels.preview import PreviewPanel, PreviewThumbnail
from voxel_qt.ui.panels.status_bar import StatusBar
from voxel_qt.ui.panels.waveforms import WaveformsPanel


class PlaceholderPanel(QWidget):
    """Placeholder panel for features not yet implemented."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {Colors.BG_DARK};")

        layout = vbox(self)

        label = Text.muted(title, color=Colors.TEXT_DISABLED)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


__all__ = [
    "ControlPanel",
    "GridPanel",
    "GridTablePanel",
    "LogPanel",
    "PlaceholderPanel",
    "PreviewPanel",
    "PreviewThumbnail",
    "StatusBar",
    "WaveformsPanel",
]
