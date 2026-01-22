# pyright: reportMissingImports=false
"""Control page - main operational interface.

Layout:
- Header bar: Profile selector, Start/Stop buttons
- Left sidebar: Channel sections (scrollable)
- Center: Preview + Grid canvas (top), Tabs (bottom)
- Status bar: Connection status, laser indicators, stage position, Exit
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from spim_qt.ui.controls import ChannelSection
from spim_qt.ui.primitives.buttons import Button
from spim_qt.ui.primitives.display import Label, Separator
from spim_qt.ui.primitives.input import Select
from spim_qt.ui.theme import Colors, Spacing

if TYPE_CHECKING:
    from spim_qt.app import SpimQtApp

log = logging.getLogger(__name__)


class PlaceholderPanel(QWidget):
    """Placeholder panel for features not yet implemented."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {Colors.BG_DARK};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = Label(title, variant="muted", color=Colors.TEXT_DISABLED)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


class LeftSidebar(QWidget):
    """Left sidebar with header (profile selector) and channel sections (scrollable)."""

    profile_changed = Signal(str)

    def __init__(self, app: SpimQtApp, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._channel_sections: dict[str, ChannelSection] = {}

        self.setMinimumWidth(280)
        self.setMaximumWidth(500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with profile selector
        header = QWidget()
        header.setFixedHeight(40)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(Spacing.MD, 0, Spacing.MD, 0)
        header_layout.setSpacing(0)

        self._profile_select = Select()
        self._profile_select.value_changed.connect(self._on_profile_changed)
        header_layout.addWidget(self._profile_select, stretch=1)

        layout.addWidget(header)
        layout.addWidget(Separator())

        # Scrollable area for channel sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {Colors.BG_DARK};
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {Colors.BG_DARK};
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {Colors.BORDER};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        self._channels_container = QWidget()
        self._channels_container.setStyleSheet(f"background-color: {Colors.BG_DARK};")
        self._channels_layout = QVBoxLayout(self._channels_container)
        self._channels_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        self._channels_layout.setSpacing(Spacing.LG)
        self._channels_layout.addStretch()

        scroll.setWidget(self._channels_container)
        layout.addWidget(scroll, stretch=1)

        # Connect to app signals
        self._app.devices_ready.connect(self._on_devices_ready)

    def _on_devices_ready(self) -> None:
        """Initialize controls when devices are ready."""
        self.rebuild_channel_sections()

    def rebuild_channel_sections(self) -> None:
        """Rebuild channel sections for the current profile."""
        rig = self._app.rig
        devices = self._app.devices

        if not rig or not devices:
            return

        # Clear existing sections
        for section in self._channel_sections.values():
            self._channels_layout.removeWidget(section)
            section.deleteLater()
        self._channel_sections.clear()

        # Remove stretch and any remaining widgets
        while self._channels_layout.count() > 0:
            item = self._channels_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Create new sections for active channels
        for channel_id, channel_config in rig.active_channels.items():
            section = ChannelSection(
                channel_id=channel_id,
                channel_config=channel_config,
                devices=devices,
            )
            self._channel_sections[channel_id] = section
            self._channels_layout.addWidget(section)

        # Add stretch at bottom
        self._channels_layout.addStretch()

    def set_profiles(self, profiles: list[str], current: str | None = None) -> None:
        """Populate the profile selector."""
        self._profile_select.set_options(profiles, current)

    def _on_profile_changed(self, profile_id: str) -> None:
        """Handle profile selection change."""
        if profile_id:
            self.profile_changed.emit(profile_id)


class StatusBar(QWidget):
    """Status bar with connection status, laser indicators, stage position, and exit button."""

    def __init__(self, app: SpimQtApp, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app

        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)
        layout.setSpacing(Spacing.MD)

        # Connection status
        self._status_dot = Label("●", variant="muted", color=Colors.TEXT_DISABLED)
        layout.addWidget(self._status_dot)

        self._status_label = Label("Connecting...", variant="muted")
        layout.addWidget(self._status_label)

        layout.addSpacing(Spacing.MD)

        # Laser indicators
        self._laser_indicators: list[Label] = []
        for wavelength in [488, 561, 594, 647]:
            dot = Label("●", variant="default", color=Colors.TEXT_DISABLED)
            dot.setToolTip(f"{wavelength}nm")
            layout.addWidget(dot)
            self._laser_indicators.append(dot)

        layout.addStretch()

        # Stage position
        self._stage_label = Label("X: 0.000  Y: 0.000  Z: 0.000", variant="value", color=Colors.TEXT_MUTED)
        layout.addWidget(self._stage_label)

        layout.addStretch()

        # Exit button using ghost variant
        self._exit_btn = Button("Exit", variant="ghost")
        self._exit_btn.clicked.connect(self._on_exit_clicked)
        layout.addWidget(self._exit_btn)

    def _on_exit_clicked(self) -> None:
        """Exit the active session."""
        asyncio.create_task(self._app.close_session())

    def set_connected(self, connected: bool) -> None:
        """Update connection status display."""
        if connected:
            self._status_dot.color = Colors.SUCCESS
            self._status_label.setText("Connected")
            self._status_label.color = Colors.SUCCESS
        else:
            self._status_dot.color = Colors.TEXT_DISABLED
            self._status_label.setText("Disconnected")
            self._status_label.color = Colors.TEXT_MUTED

    def set_laser_state(self, index: int, active: bool) -> None:
        """Set laser indicator state."""
        if 0 <= index < len(self._laser_indicators):
            self._laser_indicators[index].color = Colors.SUCCESS if active else Colors.TEXT_DISABLED

    def set_stage_position(self, x: float, y: float, z: float) -> None:
        """Update stage position display."""
        self._stage_label.setText(f"X: {x:.3f}  Y: {y:.3f}  Z: {z:.3f}")


class MainPanel(QWidget):
    """Center panel with header, preview, grid canvas, and bottom tabs."""

    def __init__(self, app: SpimQtApp, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with Start/Stop buttons
        header = QWidget()
        header.setFixedHeight(40)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(Spacing.MD, 0, Spacing.LG, 0)
        header_layout.setSpacing(Spacing.MD)

        header_layout.addStretch()

        self._start_btn = Button("Start", variant="success")
        self._start_btn.clicked.connect(self._on_start_clicked)
        header_layout.addWidget(self._start_btn)

        self._stop_btn = Button("Stop", variant="danger")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        header_layout.addWidget(self._stop_btn)

        layout.addWidget(header)
        layout.addWidget(Separator())

        # Vertical splitter for top/bottom
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {Colors.BORDER}; height: 1px; }}")

        # Top: preview and grid canvas side by side
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {Colors.BORDER}; width: 1px; }}")

        top_splitter.addWidget(PlaceholderPanel("Preview"))
        top_splitter.addWidget(PlaceholderPanel("Grid"))
        top_splitter.setSizes([500, 500])

        splitter.addWidget(top_splitter)

        # Bottom: tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; border-top: 1px solid {Colors.BORDER}; background-color: {Colors.BG_DARK}; }}
            QTabBar::tab {{ background-color: transparent; color: {Colors.TEXT_MUTED}; border: none; padding: 6px 12px; }}
            QTabBar::tab:selected {{ color: {Colors.TEXT}; border-bottom: 2px solid {Colors.ACCENT}; }}
            QTabBar::tab:hover:!selected {{ color: {Colors.TEXT}; }}
        """)

        self._tabs.addTab(PlaceholderPanel("Grid controls"), "Grid")
        self._tabs.addTab(PlaceholderPanel("Waveforms"), "Waveforms")
        self._tabs.addTab(PlaceholderPanel("Logs"), "Logs")

        splitter.addWidget(self._tabs)
        splitter.setSizes([600, 400])

        layout.addWidget(splitter)

    def _on_start_clicked(self) -> None:
        """Handle start button click."""
        log.info("Start clicked")
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        # TODO: Implement acquisition start

    def _on_stop_clicked(self) -> None:
        """Handle stop button click."""
        log.info("Stop clicked")
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        # TODO: Implement acquisition stop


class ControlPage(QWidget):
    """Main control page shown when a session is active.

    Layout:
    - Left sidebar: Header (profile selector) + Channel sections (scrollable)
    - Center: Header (Start/Stop) + Preview + Grid canvas (top splitter), Tabs (bottom)
    - Status bar: Connection status, laser indicators, stage position, Exit button
    """

    def __init__(self, app: SpimQtApp, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app

        self._setup_ui()

        # Connect to app signals
        self._app.devices_ready.connect(self._on_devices_ready)

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main content area as splitter for resizable sidebar
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {Colors.BORDER}; width: 1px; }}")

        # Left sidebar (includes its own header with profile selector)
        self._left_sidebar = LeftSidebar(self._app)
        self._left_sidebar.profile_changed.connect(self._on_profile_changed)
        content_splitter.addWidget(self._left_sidebar)

        # Center panel (includes its own header with Start/Stop buttons)
        self._center_panel = MainPanel(self._app)
        content_splitter.addWidget(self._center_panel)

        content_splitter.setSizes([320, 1080])

        layout.addWidget(content_splitter, stretch=1)

        # Status bar with connection status, laser indicators, stage position, exit
        layout.addWidget(Separator())
        self._status_bar = StatusBar(self._app)
        layout.addWidget(self._status_bar)

    def _on_devices_ready(self) -> None:
        """Initialize UI when devices are ready."""
        rig = self._app.rig
        if not rig:
            return

        # Populate profile selector
        profiles = list(rig.config.profiles.keys())
        current = rig.active_profile_id
        self._left_sidebar.set_profiles(profiles, current)

        # Update connection status
        self._status_bar.set_connected(True)

    def _on_profile_changed(self, profile_id: str) -> None:
        """Handle profile selection change from header."""
        rig = self._app.rig
        if rig:
            log.info("Switching to profile: %s", profile_id)
            asyncio.create_task(self._switch_profile(profile_id))

    async def _switch_profile(self, profile_id: str) -> None:
        """Switch to a new profile (async)."""
        rig = self._app.rig
        if rig:
            await rig.set_active_profile(profile_id)
            self._left_sidebar.rebuild_channel_sections()

    @property
    def status_bar(self) -> StatusBar:
        """Access the status bar for updates."""
        return self._status_bar

    def refresh(self) -> None:
        """Refresh the control page with current session data."""
        log.debug("Refreshing control page")
        # TODO: Update UI with session data
