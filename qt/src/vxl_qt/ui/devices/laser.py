"""Laser device control widget."""

import logging
from typing import Any

from PySide6.QtWidgets import QVBoxLayout, QWidget

from vxl_qt.handle import DeviceHandleQt
from vxl_qt.ui.kit import (
    Color,
    Colors,
    Flex,
    LockableSlider,
    Spacing,
    Stretch,
    Text,
    Toggle,
)
from vxlib import fire_and_forget

log = logging.getLogger(__name__)


class LaserControl(QWidget):
    """Laser device control widget.

    Displays:
    - Header: Wavelength chip + power readout + enable toggle
    - Power setpoint slider

    Wrapped in a CardDark container.

    Args:
        adapter: DeviceHandleQt wrapping a laser device.
        parent: Parent widget.

    Example (integrated with vxl-qt):
        adapter = devices_manager.get_adapter("laser_488")
        widget = LaserControl(adapter)

    Example (standalone):
        from vxl_drivers.lasers.simulated import SimulatedLaser
        from rigup import create_local_handle
        from vxl_qt.handle import DeviceHandleQt

        device = SimulatedLaser(uid="laser", wavelength=488, max_power_mw=100)
        handle = create_local_handle(device)
        adapter = DeviceHandleQt(handle)
        await adapter.start()
        widget = LaserControl(adapter)
    """

    def __init__(self, adapter: DeviceHandleQt, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._adapter = adapter
        self._wavelength: int | None = None
        self._color = Colors.ACCENT

        # Outer layout
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Header widgets
        self._label = Text.heading("Laser")
        self._power_label = Text.value("-- mW", color=Colors.TEXT_MUTED)
        self._enable_toggle = Toggle()
        self._enable_toggle.setToolTip("Enable/disable laser emission")

        # Header row: label + stretch + power label + toggle
        header = Flex.hstack(self._label, Stretch(), self._power_label, self._enable_toggle)

        # Power slider
        self._power_slider = LockableSlider(
            min_value=0.0,
            max_value=100.0,
            color=self._color,
        )

        # Card container with all content
        content = Flex.card(header, self._power_slider, spacing=Spacing.SM)
        outer_layout.addWidget(content)

        # Connect signals
        self._adapter.properties_changed.connect(self._on_properties_changed)
        self._enable_toggle.toggled.connect(self._on_toggle_changed)
        self._power_slider.inputReleased.connect(self._on_power_changed)

        # Request initial property values
        self._adapter.request_initial_properties()

    def _on_properties_changed(self, props: dict[str, Any]) -> None:
        """Update UI from device properties."""
        if "wavelength" in props:
            wavelength = int(props["wavelength"])
            if self._wavelength != wavelength:
                self._wavelength = wavelength
                self._color = Color.from_wavelength(wavelength)
                self._label.setText(f"Laser - {wavelength} nm")
                self._power_slider.setColor(self._color)
                self._enable_toggle.setColor(self._color)

        if "is_enabled" in props:
            is_enabled = bool(props["is_enabled"])
            self._enable_toggle.blockSignals(True)
            self._enable_toggle.setChecked(is_enabled)
            self._enable_toggle.blockSignals(False)

        if "power_setpoint_mw" in props:
            setpoint = float(props["power_setpoint_mw"])
            self._power_slider.setTarget(setpoint)

        if "power_mw" in props:
            power = float(props["power_mw"])
            self._power_slider.setActual(power)
            self._power_label.setText(f"{power:.1f} mW")

    def _on_toggle_changed(self, checked: bool) -> None:
        """Handle enable toggle change."""
        command = "enable" if checked else "disable"
        fire_and_forget(self._adapter.call(command), log=log)
        log.debug("Laser %s: %s", self._adapter.uid, command)

    def _on_power_changed(self, value: float) -> None:
        """Handle power setpoint change from slider."""
        fire_and_forget(self._adapter.set("power_setpoint_mw", value), log=log)
        log.debug("Laser %s: set power_setpoint_mw = %.1f", self._adapter.uid, value)

    def update_power_range(self, min_val: float, max_val: float) -> None:
        """Update the power slider range (call after fetching device interface)."""
        self._power_slider.setRange(min_val, max_val)
