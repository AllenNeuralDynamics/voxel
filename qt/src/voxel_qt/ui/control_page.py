# pyright: reportMissingImports=false
"""Control page - main operational interface.

Layout:
- Header bar: Profile selector, Preview toggle button
- Left sidebar: Channel sections (scrollable)
- Center: Preview + Grid canvas (top), Tabs (bottom)
- Status bar: Connection status, laser indicators, stage position, Exit
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabWidget, QWidget

from voxel_qt.ui.kit import Colors, Separator, Splitter, vbox
from voxel_qt.ui.panels import ControlPanel, GridPanel, LogPanel, PlaceholderPanel, PreviewPanel, StatusBar
from vxlib import fire_and_forget

if TYPE_CHECKING:
    from voxel_qt.app import VoxelApp

log = logging.getLogger(__name__)


class ControlPage(QWidget):
    """Main control page shown when a session is active.

    Layout:
    - Left sidebar: Header (profile selector) + Channel sections (scrollable)
    - Center: Preview + Grid canvas (top splitter), Tabs (bottom)
    - Status bar: Connection status, laser indicators, stage position, Exit button
    """

    def __init__(self, app: "VoxelApp", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app

        # Left sidebar with profile selector and channel controls
        self._left_sidebar = ControlPanel(self._app)
        self._left_sidebar.profile_changed.connect(self._on_profile_changed)

        # Preview widget (reads from app.preview store)
        self._preview_widget = PreviewPanel(self._app.preview)

        # Status bar
        self._status_bar = StatusBar(self._app)

        self._configure_layout()

        # Connect to app signals
        self._app.devices_ready.connect(self._on_devices_ready)

    def _configure_layout(self) -> None:
        """Set up the UI."""
        layout = vbox(self)

        # Main content area as splitter for resizable sidebar
        content_splitter = Splitter(Qt.Orientation.Horizontal)
        content_splitter.addWidget(self._left_sidebar)

        # Center panel: vertical splitter for top/bottom
        center_splitter = Splitter(Qt.Orientation.Vertical)

        # Top: preview and grid canvas side by side
        top_splitter = Splitter(Qt.Orientation.Horizontal)
        top_splitter.addWidget(self._preview_widget)
        top_splitter.addWidget(GridPanel(self._app.preview))
        top_splitter.setSizes([500, 500])
        center_splitter.addWidget(top_splitter)

        # Bottom: tabs
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                border-top: 1px solid {Colors.BORDER};
                background-color: {Colors.BG_DARK};
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED};
                border: none;
                border-bottom: 2px solid transparent;
                padding: 6px 12px;
            }}
            QTabBar::tab:selected {{
                color: {Colors.TEXT};
                border-bottom: 2px solid {Colors.ACCENT};
            }}
            QTabBar::tab:hover:!selected {{ color: {Colors.TEXT}; }}
        """)
        tabs.addTab(PlaceholderPanel("Grid controls"), "Grid")
        tabs.addTab(PlaceholderPanel("Waveforms"), "Waveforms")
        tabs.addTab(LogPanel(), "Logs")
        center_splitter.addWidget(tabs)
        center_splitter.setSizes([600, 400])

        content_splitter.addWidget(center_splitter)
        content_splitter.setSizes([320, 1080])

        layout.addWidget(content_splitter, stretch=1)

        # Status bar
        layout.addWidget(Separator())
        layout.addWidget(self._status_bar)

    def _on_devices_ready(self) -> None:
        """Initialize UI when devices are ready."""
        rig = self._app.rig
        if not rig:
            return

        # Update connection status
        self._status_bar.set_connected(True)

    def _on_profile_changed(self, profile_id: str) -> None:
        """Handle profile selection change from header."""
        rig = self._app.rig
        if rig:
            log.info("Switching to profile: %s", profile_id)
            fire_and_forget(self._switch_profile(profile_id), log=log)

    async def _switch_profile(self, profile_id: str) -> None:
        """Switch to a new profile (async)."""
        rig = self._app.rig
        if rig:
            await rig.set_active_profile(profile_id)
            self._left_sidebar.rebuild_channel_sections()

    def refresh(self) -> None:
        """Refresh the control page with current session data."""
        log.debug("Refreshing control page")
        # TODO: Update UI with session data
