# pyright: reportMissingImports=false
"""Control page - main operational interface.

Layout:
- Left sidebar: Header (profile selector) + Channel sections + Footer (connection, exit)
- Center: Preview + Grid canvas (top), Tabs with inline status bar (bottom)
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStackedWidget, QWidget

from voxel_qt.ui.kit import Box, Color, Colors, FontSize, Separator, Size, Spacing, Splitter, Stretch, Text, vbox
from voxel_qt.ui.panels import (
    ControlPanel,
    GridCanvas,
    GridPanel,
    LogPanel,
    PlaceholderPanel,
    PreviewPanel,
)
from vxlib import fire_and_forget

if TYPE_CHECKING:
    from voxel_qt.app import VoxelApp

log = logging.getLogger(__name__)


class TabButton(QWidget):
    """A single tab button for the custom tab bar."""

    def __init__(self, label: str, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index
        self._selected = False

        self._label = Text.muted(label)
        self._label.setStyleSheet("""
            padding: 6px 12px;
            border-top: 2px solid transparent;
        """)

        layout = vbox(self, margins=(0, 0, 0, 0))
        layout.addWidget(self._label)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def index(self) -> int:
        return self._index

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self._label.setStyleSheet(f"""
                color: {Colors.ACCENT};
                padding: 6px 12px;
                border-top: 2px solid {Colors.ACCENT};
            """)
        else:
            self._label.setStyleSheet(f"""
                color: {Colors.TEXT_MUTED};
                padding: 6px 12px;
                border-top: 2px solid transparent;
            """)

    def mousePressEvent(self, _event) -> None:  # type: ignore[override]
        # Find parent TabbedPanel and switch tab
        parent = self.parent()
        while parent and not isinstance(parent, TabbedPanel):
            parent = parent.parent()
        if parent:
            parent.set_current_index(self._index)

    def enterEvent(self, _event) -> None:  # type: ignore[override]
        if not self._selected:
            self._label.setStyleSheet(f"""
                color: {Colors.TEXT};
                padding: 6px 12px;
                border-top: 2px solid transparent;
            """)

    def leaveEvent(self, _event) -> None:  # type: ignore[override]
        if not self._selected:
            self._label.setStyleSheet(f"""
                color: {Colors.TEXT_MUTED};
                padding: 6px 12px;
                border-top: 2px solid transparent;
            """)


class TabbedPanel(QWidget):
    """Custom tabbed panel with tab bar at bottom and status bar inline."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tabs: list[TabButton] = []
        self._current_index = 0

        # Content stack
        self._stack = QStackedWidget()

        # Bottom bar: tabs on left, status bar slot on right
        self._tab_bar = Box.hstack(spacing=0)
        self._status_container = Box.hstack(spacing=Spacing.MD)

        bottom_bar = Box.hstack(
            self._tab_bar,
            Stretch(),
            self._status_container,
            spacing=0,
            padding=(0, 0, Spacing.LG, 0),
        )

        # Main layout
        layout = vbox(self, spacing=0)
        layout.addWidget(self._stack, stretch=1)
        layout.addWidget(Separator())
        layout.addWidget(bottom_bar)

    def add_tab(self, widget: QWidget, label: str) -> None:
        """Add a tab with the given widget and label."""
        index = len(self._tabs)
        tab_btn = TabButton(label, index)
        self._tabs.append(tab_btn)
        self._tab_bar.add(tab_btn)
        self._stack.addWidget(widget)

        # Select first tab by default
        if index == 0:
            tab_btn.set_selected(True)

    def set_status_widget(self, widget: QWidget) -> None:
        """Set the status widget to display on the right side of the tab bar."""
        self._status_container.add(widget)

    def set_current_index(self, index: int) -> None:
        """Switch to the tab at the given index."""
        if 0 <= index < len(self._tabs):
            # Deselect old
            if 0 <= self._current_index < len(self._tabs):
                self._tabs[self._current_index].set_selected(False)
            # Select new
            self._current_index = index
            self._tabs[index].set_selected(True)
            self._stack.setCurrentIndex(index)


class MainFooter(QWidget):
    """Footer with laser indicators and stage position, inline with tab bar."""

    def __init__(self, app: "VoxelApp", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app

        self.setFixedHeight(Size.XL)

        # Stage position (left)
        self._stage_label = Text.value("X: 0.000  Y: 0.000  Z: 0.000", color=Colors.TEXT_MUTED)

        # Laser indicators (right)
        self._laser_box = Box.hstack(spacing=Spacing.XS)
        self._laser_indicators: dict[str, Text] = {}

        # Layout: stage position on left, laser indicators on right
        content = Box.hstack(
            self._stage_label,
            self._laser_box,
            spacing=Spacing.LG,
            padding=(Spacing.MD, 0, Spacing.MD, 0),
        )

        layout = vbox(self, margins=(0, 0, 0, 0))
        layout.addWidget(content)

        # Connect to devices ready signal
        self._app.devices_ready.connect(self._on_devices_ready)

    def _on_devices_ready(self) -> None:
        """Set up laser indicators when devices are ready."""
        devices = self._app.devices
        if not devices:
            return

        # Clear existing indicators
        self._laser_box.clear()
        self._laser_indicators.clear()

        # Create indicators for each laser
        for uid, adapter in devices.get_lasers().items():
            dot = Text.default("●", color=Colors.TEXT_DISABLED, size=FontSize.XS)
            self._laser_box.add(dot)
            self._laser_indicators[uid] = dot

            # Connect to property changes
            adapter.properties_changed.connect(lambda props, u=uid: self._on_laser_props(u, props))
            adapter.request_initial_properties()

    def _on_laser_props(self, uid: str, props: dict) -> None:
        """Handle laser property updates."""
        if uid not in self._laser_indicators:
            return

        indicator = self._laser_indicators[uid]

        # Update tooltip with wavelength
        if "wavelength" in props:
            wavelength = int(props["wavelength"])
            indicator.setToolTip(f"{wavelength}nm")

        # Update color based on enabled state and wavelength
        if "is_enabled" in props:
            is_enabled = bool(props["is_enabled"])
            devices = self._app.devices
            if devices:
                wavelength = devices.get_property(uid, "wavelength")
                if is_enabled and wavelength:
                    indicator.fmt = indicator.fmt.with_(color=Color.from_wavelength(int(wavelength)))
                else:
                    indicator.fmt = indicator.fmt.with_(color=Colors.TEXT_DISABLED)

    def set_stage_position(self, x: float, y: float, z: float) -> None:
        """Update stage position display."""
        self._stage_label.setText(f"X: {x:.3f}  Y: {y:.3f}  Z: {z:.3f}")


class ControlPage(QWidget):
    """Main control page shown when a session is active.

    Layout:
    - Left sidebar: Header (profile selector) + Channel sections + Footer (connection, exit)
    - Center: Preview + Grid canvas (top), Tabs with inline status bar (bottom)
    """

    def __init__(self, app: "VoxelApp", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app

        # Left sidebar with profile selector and channel controls
        self._left_sidebar = ControlPanel(self._app)
        self._left_sidebar.profile_changed.connect(self._on_profile_changed)

        # Preview widget (reads from app.preview store)
        self._preview_widget = PreviewPanel(self._app.preview)

        # Main footer (embedded in tab bar)
        self._main_footer = MainFooter(self._app)

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

        # Top: preview and grid panel side by side
        top_splitter = Splitter(Qt.Orientation.Horizontal)
        top_splitter.addWidget(self._preview_widget)
        top_splitter.addWidget(GridCanvas(self._app.preview, self._app.grid))
        top_splitter.setSizes([500, 500])
        center_splitter.addWidget(top_splitter)

        # Bottom: custom tabbed panel with inline footer
        tabbed_panel = TabbedPanel()
        tabbed_panel.add_tab(GridPanel(self._app.grid), "Grid")
        tabbed_panel.add_tab(PlaceholderPanel("Waveforms"), "Waveforms")
        tabbed_panel.add_tab(LogPanel(), "Logs")
        tabbed_panel.set_status_widget(self._main_footer)

        center_splitter.addWidget(tabbed_panel)
        center_splitter.setSizes([600, 400])

        content_splitter.addWidget(center_splitter)
        content_splitter.setSizes([320, 1080])

        layout.addWidget(content_splitter, stretch=1)

    def _on_devices_ready(self) -> None:
        """Initialize UI when devices are ready."""
        rig = self._app.rig
        if not rig:
            return

        # Update connection status in left sidebar
        self._left_sidebar.set_connected(True)

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
