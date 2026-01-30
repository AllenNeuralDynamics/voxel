"""Panel components for the control page."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from vxl_qt.ui.kit import Colors, Text, vbox
from vxl_qt.ui.panels.controls import ControlPanel
from vxl_qt.ui.panels.grid import GridCanvas, GridPanel
from vxl_qt.ui.panels.logs import LogPanel
from vxl_qt.ui.panels.preview import PreviewPanel, PreviewThumbnail
from vxl_qt.ui.panels.waveforms import WaveformsPanel


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
    "GridCanvas",
    "GridPanel",
    "LogPanel",
    "PlaceholderPanel",
    "PreviewPanel",
    "PreviewThumbnail",
    "WaveformsPanel",
]
