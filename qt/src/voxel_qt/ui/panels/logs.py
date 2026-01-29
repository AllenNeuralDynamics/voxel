"""Log panel for displaying application logs."""

import logging

from PySide6.QtWidgets import QTextEdit, QWidget

from voxel_qt.ui.assets import DEFAULT_FAMILY
from voxel_qt.ui.kit import Colors, vbox


class LogPanel(QWidget):
    """Panel for displaying application logs with color-coded levels."""

    def __init__(self, level: int = logging.INFO, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = vbox(self)

        # Log text area
        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Colors.BG_DARK};
                border: none;
                color: {Colors.TEXT};
                font-family: {DEFAULT_FAMILY.mono.css};
                font-size: 11px;
            }}
        """)
        layout.addWidget(self._log_area)

        # Set up log handler
        self._handler = _LogHandler(self._append_log)
        self._handler.setLevel(level)
        self._handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%H:%M:%S"))

        # Add to root logger
        logging.getLogger().addHandler(self._handler)

    def _append_log(self, message: str, level: str) -> None:
        """Append a log message to the display."""
        color = _level_color(level)
        self._log_area.append(f'<span style="color: {color}">{message}</span>')

    def clear(self) -> None:
        """Clear the log display."""
        self._log_area.clear()

    def set_level(self, level: int) -> None:
        """Set the minimum log level to display."""
        self._handler.setLevel(level)


def _level_color(level: str) -> str:
    """Get color for a log level."""
    return {
        "DEBUG": Colors.TEXT_MUTED,
        "INFO": Colors.TEXT,
        "WARNING": Colors.WARNING,
        "ERROR": Colors.ERROR,
        "CRITICAL": Colors.ERROR,
    }.get(level, Colors.TEXT)


class _LogHandler(logging.Handler):
    """Log handler that forwards to a LogPanel callback."""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            self._callback(message, record.levelname)
        except Exception:
            self.handleError(record)
