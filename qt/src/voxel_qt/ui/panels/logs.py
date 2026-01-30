"""Log panel for displaying application logs."""

import logging
from collections.abc import Callable

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from voxel_qt.ui.assets import DEFAULT_FAMILY
from voxel_qt.ui.kit import Colors, FontSize, Spacing, vbox

# Log level icons (matching web version)
LEVEL_ICONS: dict[str, str] = {
    "DEBUG": "mdi.bug-outline",
    "INFO": "mdi.information-outline",
    "WARNING": "mdi.alert-outline",
    "ERROR": "mdi.alert-circle-outline",
    "CRITICAL": "mdi.alert-octagon-outline",
}

LEVEL_COLORS: dict[str, str] = {
    "DEBUG": Colors.TEXT_MUTED,
    "INFO": Colors.TEXT_MUTED,
    "WARNING": Colors.WARNING,
    "ERROR": Colors.ERROR,
    "CRITICAL": Colors.ERROR,
}


class LogPanel(QWidget):
    """Panel for displaying application logs with color-coded levels."""

    def __init__(self, level: int = logging.INFO, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = vbox(self)

        # Scroll area for log entries
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {Colors.BG_DARK};
                border: none;
            }}
        """)

        # Container for log entries
        self._container = QWidget()
        self._container.setStyleSheet(f"background-color: {Colors.BG_DARK};")
        self._log_layout = QVBoxLayout(self._container)
        self._log_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        self._log_layout.setSpacing(2)
        self._log_layout.addStretch()  # Push entries to top

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)

        # Set up log handler
        self._handler = _LogHandler(self._append_log)
        self._handler.setLevel(level)
        self._handler.setFormatter(logging.Formatter("%(asctime)s", "%H:%M:%S"))

        # Add to root logger
        logging.getLogger().addHandler(self._handler)

    def _append_log(self, record: logging.LogRecord) -> None:
        """Append a log message to the display."""
        entry = _LogEntry(record)

        # Insert before the stretch
        self._log_layout.insertWidget(self._log_layout.count() - 1, entry)

        # Auto-scroll to bottom
        self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum())

    def clear(self) -> None:
        """Clear the log display."""
        # Remove all widgets except the stretch
        while self._log_layout.count() > 1:
            item = self._log_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.deleteLater()

    def set_level(self, level: int) -> None:
        """Set the minimum log level to display."""
        self._handler.setLevel(level)


class _LogEntry(QWidget):
    """Single log entry widget with time, logger, message, and level icon."""

    def __init__(self, record: logging.LogRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        level = record.levelname
        color = LEVEL_COLORS.get(level, Colors.TEXT)
        icon_name = LEVEL_ICONS.get(level, "mdi.circle-small")

        # Format time
        time_str = logging.Formatter("%(asctime)s", "%H:%M:%S").format(record)

        # Truncate logger name if too long
        logger_name = _truncate_middle(record.name, 28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        # Time (fixed width)
        time_label = QLabel(time_str)
        time_label.setFixedWidth(60)
        time_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED};
            font-family: {DEFAULT_FAMILY.mono.css};
            font-size: {FontSize.XS}px;
        """)
        layout.addWidget(time_label)

        # Logger name (fixed width)
        logger_label = QLabel(logger_name)
        logger_label.setFixedWidth(180)
        logger_label.setToolTip(record.name)
        logger_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED};
            font-family: {DEFAULT_FAMILY.mono.css};
            font-size: {FontSize.XS}px;
        """)
        layout.addWidget(logger_label)

        # Message (stretches)
        msg_label = QLabel(record.getMessage())
        msg_label.setStyleSheet(f"""
            color: {Colors.TEXT};
            font-family: {DEFAULT_FAMILY.mono.css};
            font-size: {FontSize.XS}px;
        """)
        layout.addWidget(msg_label, 1)

        # Level icon (right-aligned)
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon(icon_name, color=QColor(color)).pixmap(14, 14))
        icon_label.setToolTip(level)
        icon_label.setFixedWidth(20)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(icon_label)


def _truncate_middle(text: str, max_len: int) -> str:
    """Truncate string in the middle if too long."""
    if len(text) <= max_len:
        return text
    half = (max_len - 1) // 2
    return text[:half] + "…" + text[-(max_len - half - 1) :]


class _LogHandler(logging.Handler):
    """Log handler that forwards to a LogPanel callback."""

    def __init__(self, callback: Callable[[logging.LogRecord], None]) -> None:
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._callback(record)
        except Exception:
            self.handleError(record)
