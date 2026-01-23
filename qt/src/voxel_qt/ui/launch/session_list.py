"""Session list widget for displaying recent sessions."""

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from voxel_studio.system import SessionDirectory

from voxel_qt.ui.primitives.display import Chip, Label
from voxel_qt.ui.theme import Colors


class SessionListItem(QWidget):
    """Custom widget for displaying a session in the list."""

    def __init__(self, session: SessionDirectory, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Top row: session name and rig name
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        top_row.addWidget(Label(session.name, variant="default", color=Colors.TEXT_BRIGHT))
        top_row.addWidget(Chip(session.rig_name, color=Colors.BG_LIGHT))
        top_row.addStretch()

        layout.addLayout(top_row)

        # Bottom row: root name and modified time
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        bottom_row.addWidget(Label(session.root_name, variant="muted"))

        # Format modified time
        modified_str = self._format_modified(session.modified)
        bottom_row.addStretch()
        bottom_row.addWidget(Label(modified_str, variant="muted"))

        layout.addLayout(bottom_row)

    @property
    def session(self) -> SessionDirectory:
        """Get the session data."""
        return self._session

    def _format_modified(self, dt: datetime) -> str:
        """Format the modified time for display."""
        now = datetime.now()
        delta = now - dt

        if delta.days == 0:
            if delta.seconds < 3600:
                minutes = delta.seconds // 60
                return f"{minutes}m ago" if minutes > 0 else "just now"
            hours = delta.seconds // 3600
            return f"{hours}h ago"
        if delta.days == 1:
            return "yesterday"
        if delta.days < 7:
            return f"{delta.days}d ago"
        return dt.strftime("%b %d, %Y")


class SessionList(QWidget):
    """List widget for displaying and selecting recent sessions.

    Emits:
        session_selected: When a session is double-clicked
    """

    session_selected = Signal(object)  # SessionDirectory

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {Colors.BG_MEDIUM};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {Colors.BORDER};
                padding: 0px;
            }}
            QListWidget::item:selected {{
                background-color: {Colors.BG_LIGHT};
            }}
            QListWidget::item:hover {{
                background-color: {Colors.HOVER};
            }}
        """)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        self._sessions: list[SessionDirectory] = []

    def set_sessions(self, sessions: list[SessionDirectory]) -> None:
        """Update the list with new sessions."""
        self._sessions = sessions
        self._list.clear()

        for session in sessions:
            item = QListWidgetItem(self._list)
            widget = SessionListItem(session)
            item.setSizeHint(widget.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on a session."""
        widget = self._list.itemWidget(item)
        if isinstance(widget, SessionListItem):
            self.session_selected.emit(widget.session)

    def set_loading(self, loading: bool) -> None:
        """Show/hide loading state."""
        if loading:
            self._list.clear()
            item = QListWidgetItem("Loading sessions...")
            item.setFlags(item.flags() & ~item.flags())  # Disable selection
            self._list.addItem(item)
