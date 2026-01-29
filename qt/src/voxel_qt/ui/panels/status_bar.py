"""Status bar panel with connection status, laser indicators, stage position, and exit button."""

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from voxel_qt.ui.kit import Button, Color, Colors, Spacing, Text, hbox
from vxlib import fire_and_forget

if TYPE_CHECKING:
    from voxel_qt.app import VoxelApp

log = logging.getLogger(__name__)


class StatusBar(QWidget):
    """Status bar with connection status, laser indicators, stage position, and exit button."""

    def __init__(self, app: "VoxelApp", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app

        self.setFixedHeight(32)

        layout = hbox(self, spacing=Spacing.MD, margins=(Spacing.LG, 0, Spacing.LG, 0))

        # Connection status
        self._status_dot = Text.muted("●", color=Colors.TEXT_DISABLED)
        layout.addWidget(self._status_dot)

        self._status_label = Text.muted("Connecting...")
        layout.addWidget(self._status_label)

        layout.addStretch()

        # Center section: laser indicators container + stage position
        self._laser_container = QWidget()
        self._laser_layout = hbox(self._laser_container, spacing=Spacing.SM)
        layout.addWidget(self._laser_container)

        self._laser_indicators: dict[str, Text] = {}  # uid -> indicator

        layout.addSpacing(Spacing.LG)

        # Stage position
        self._stage_label = Text.value("X: 0.000  Y: 0.000  Z: 0.000", color=Colors.TEXT_MUTED)
        layout.addWidget(self._stage_label)

        layout.addStretch()

        # Exit button using ghost variant
        self._exit_btn = Button.ghost("Exit")
        self._exit_btn.clicked.connect(self._on_exit_clicked)
        layout.addWidget(self._exit_btn)

        # Connect to devices ready signal
        self._app.devices_ready.connect(self._on_devices_ready)

    def _on_exit_clicked(self) -> None:
        """Exit the active session."""
        fire_and_forget(self._app.close_session(), log=log)

    def _on_devices_ready(self) -> None:
        """Set up laser indicators when devices are ready."""
        devices = self._app.devices
        if not devices:
            return

        # Clear existing indicators
        for indicator in self._laser_indicators.values():
            self._laser_layout.removeWidget(indicator)
            indicator.deleteLater()
        self._laser_indicators.clear()

        # Create indicators for each laser
        for uid, adapter in devices.get_lasers().items():
            dot = Text.default("●", color=Colors.TEXT_DISABLED)
            self._laser_layout.addWidget(dot)
            self._laser_indicators[uid] = dot

            # Connect to property changes
            adapter.properties_changed.connect(lambda props, uid=uid: self._on_laser_props(uid, props))
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
            # Get wavelength from cache
            devices = self._app.devices
            if devices:
                wavelength = devices.get_property(uid, "wavelength")
                if is_enabled and wavelength:
                    indicator.fmt = indicator.fmt.with_(color=Color.from_wavelength(int(wavelength)))
                else:
                    indicator.fmt = indicator.fmt.with_(color=Colors.TEXT_DISABLED)

    def set_connected(self, connected: bool) -> None:
        """Update connection status display."""
        if connected:
            self._status_dot.fmt = self._status_dot.fmt.with_(color=Colors.SUCCESS)
            self._status_label.setText("Connected")
            self._status_label.fmt = self._status_label.fmt.with_(color=Colors.SUCCESS)
        else:
            self._status_dot.fmt = self._status_dot.fmt.with_(color=Colors.TEXT_DISABLED)
            self._status_label.setText("Disconnected")
            self._status_label.fmt = self._status_label.fmt.with_(color=Colors.TEXT_MUTED)

    def set_stage_position(self, x: float, y: float, z: float) -> None:
        """Update stage position display."""
        self._stage_label.setText(f"X: {x:.3f}  Y: {y:.3f}  Z: {z:.3f}")
