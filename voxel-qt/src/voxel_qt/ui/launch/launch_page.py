"""Launch page for session management.

The launch page is shown when no session is active. It allows users to:
- Create new sessions
- Resume existing sessions
- View application logs
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from voxel_qt.ui.launch.new_session_form import NewSessionForm
from voxel_qt.ui.launch.session_list import SessionList
from voxel_qt.ui.primitives.display import Label
from voxel_qt.ui.theme import Colors

if TYPE_CHECKING:
    from voxel_qt.app import VoxelQtApp
    from voxel_studio.system import SessionDirectory

log = logging.getLogger(__name__)


class LogPanel(QWidget):
    """Panel for displaying application logs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Header
        layout.addWidget(Label("Logs", variant="section"))

        # Log text area
        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Colors.BG_DARK};
                border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT};
            }}
        """)
        layout.addWidget(self._log_area)

        # Set up log handler
        self._setup_log_handler()

    def _setup_log_handler(self) -> None:
        """Set up a log handler to capture logs to this widget."""
        handler = _QtLogHandler(self._append_log)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%H:%M:%S"))

        # Add to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

    def _append_log(self, message: str, level: str) -> None:
        """Append a log message to the display."""
        # Color based on level
        color = Colors.TEXT
        if level == "ERROR":
            color = Colors.ERROR
        elif level == "WARNING":
            color = Colors.WARNING
        elif level == "DEBUG":
            color = Colors.TEXT_MUTED

        self._log_area.append(f'<span style="color: {color}">{message}</span>')

    def clear(self) -> None:
        """Clear the log display."""
        self._log_area.clear()


class _QtLogHandler(logging.Handler):
    """Log handler that forwards to a Qt callback."""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            self._callback(message, record.levelname)
        except Exception:
            self.handleError(record)


class LaunchPage(QWidget):
    """Launch page for session management.

    Layout:
    - Left panel (40%): New session form + recent sessions list
    - Right panel (60%): Log viewer
    """

    def __init__(self, app: VoxelQtApp, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app

        self._setup_ui()
        self._connect_signals()
        self._load_data()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main splitter
        splitter = QSplitter()
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Colors.BORDER};
                width: 1px;
            }}
        """)

        # Left panel - session management
        left_panel = QWidget()
        left_panel.setStyleSheet(f"background-color: {Colors.BG_DARK};")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(32, 32, 32, 32)
        left_layout.setSpacing(24)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        header_layout.addWidget(Label("Voxel Qt", variant="title", color=Colors.TEXT_BRIGHT))
        header_layout.addWidget(Label("Select or create a session to get started", variant="muted"))

        left_layout.addLayout(header_layout)

        # New session form
        form_section = QVBoxLayout()
        form_section.setSpacing(8)

        form_section.addWidget(Label("New Session", variant="section", color=Colors.TEXT))

        self._new_session_form = NewSessionForm()
        form_section.addWidget(self._new_session_form)

        left_layout.addLayout(form_section)

        # Recent sessions
        sessions_section = QVBoxLayout()
        sessions_section.setSpacing(8)

        sessions_section.addWidget(Label("Recent Sessions", variant="section", color=Colors.TEXT))

        self._session_list = SessionList()
        sessions_section.addWidget(self._session_list, stretch=1)

        left_layout.addLayout(sessions_section, stretch=1)

        splitter.addWidget(left_panel)

        # Right panel - logs
        right_panel = QWidget()
        right_panel.setStyleSheet(f"background-color: {Colors.BG_MEDIUM};")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)

        self._log_panel = LogPanel()
        right_layout.addWidget(self._log_panel)

        splitter.addWidget(right_panel)

        # Set initial sizes (40% / 60%)
        splitter.setSizes([400, 600])

        layout.addWidget(splitter)

    def _connect_signals(self) -> None:
        """Connect signals."""
        self._new_session_form.session_requested.connect(self._on_new_session_requested)
        self._session_list.session_selected.connect(self._on_session_selected)

    def _load_data(self) -> None:
        """Load initial data."""
        # Load roots and rigs
        self._new_session_form.set_roots(self._app.session_roots)
        self._new_session_form.set_rigs(self._app.available_rigs)

        # Load sessions
        self._refresh_sessions()

    def _refresh_sessions(self) -> None:
        """Refresh the session list."""
        sessions = self._app.list_all_sessions()
        self._session_list.set_sessions(sessions)

    @Slot(str, str, str)
    def _on_new_session_requested(self, root_name: str, session_name: str, rig_config: str) -> None:
        """Handle new session request."""
        log.info("Creating new session: %s/%s with rig %s", root_name, session_name, rig_config)
        asyncio.create_task(self._launch_session(root_name, session_name, rig_config))

    @Slot(object)
    def _on_session_selected(self, session: SessionDirectory) -> None:
        """Handle session selection (resume)."""
        log.info("Resuming session: %s/%s", session.root_name, session.name)
        asyncio.create_task(self._launch_session(session.root_name, session.name))

    async def _launch_session(
        self,
        root_name: str,
        session_name: str,
        rig_config: str | None = None,
    ) -> None:
        """Launch a session asynchronously."""
        try:
            await self._app.launch_session(root_name, session_name, rig_config)
        except Exception as e:
            log.error("Failed to launch session: %s", e)

    def showEvent(self, event) -> None:
        """Refresh data when shown."""
        super().showEvent(event)
        self._load_data()
