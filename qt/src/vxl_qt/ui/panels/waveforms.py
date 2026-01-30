"""Waveforms panel placeholder."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from vxl_qt.ui.kit import Colors, Text, vbox


class WaveformsPanel(QWidget):
    """Waveforms panel for displaying DAQ waveform visualization."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {Colors.BG_DARK};")

        layout = vbox(self)

        label = Text.muted("Waveforms", color=Colors.TEXT_DISABLED)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
