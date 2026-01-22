"""Laser device control widget."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from voxel_qt.ui.primitives.containers import CardDark
from voxel_qt.ui.primitives.display import Chip, Label
from voxel_qt.ui.primitives.input import LockableSlider, Toggle
from voxel_qt.ui.theme import (
    BorderRadius,
    Colors,
    Spacing,
    darken_color,
    lighten_color,
    wavelength_to_hex,
)

if TYPE_CHECKING:
    from voxel_qt.handle import DeviceHandleQt

log = logging.getLogger(__name__)


class WavelengthChip(Chip):
    """Chip displaying laser wavelength with color derived from the wavelength."""

    def __init__(self, wavelength: int, parent: QWidget | None = None) -> None:
        base_color = wavelength_to_hex(wavelength)
        bg_color = lighten_color(base_color, factor=0.3)
        border_color = darken_color(base_color, factor=0.3)

        super().__init__(
            text=f"{wavelength} nm",
            color=bg_color,
            border_color=border_color,
            parent=parent,
        )
        self._wavelength = wavelength

    @property
    def wavelength(self) -> int:
        return self._wavelength


class LaserControl(QWidget):
    """Laser device control widget.

    Displays:
    - Header: Wavelength chip + power readout + enable toggle
    - Power setpoint slider

    Wrapped in a CardDark container.

    Args:
        adapter: DeviceHandleQt wrapping a laser device.
        parent: Parent widget.

    Example (integrated with voxel-qt):
        adapter = devices_manager.get_adapter("laser_488")
        widget = LaserControl(adapter)

    Example (standalone):
        from voxel_drivers.lasers.simulated import SimulatedLaser
        from pyrig import create_local_handle
        from voxel_qt.handle import DeviceHandleQt

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

        # Content container
        content = CardDark(border_radius=BorderRadius.LG)
        existing_layout = content.layout()
        assert isinstance(existing_layout, QVBoxLayout)
        content_layout = existing_layout
        content_layout.setSpacing(Spacing.SM)

        # Header row: wavelength chip + stretch + power label + toggle
        self._header_layout = QHBoxLayout()
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(Spacing.SM)

        # Wavelength chip (placeholder until we get device info)
        self._wavelength_chip: WavelengthChip | None = None
        self._chip_placeholder = Label("Laser", variant="default", color=Colors.TEXT)
        self._header_layout.addWidget(self._chip_placeholder)

        self._header_layout.addStretch()

        # Power readout
        self._power_label = Label("-- mW", variant="value", color=Colors.TEXT_MUTED)
        self._header_layout.addWidget(self._power_label)

        # Enable toggle
        self._enable_toggle = Toggle()
        self._enable_toggle.setToolTip("Enable/disable laser emission")
        self._header_layout.addWidget(self._enable_toggle)

        content_layout.addLayout(self._header_layout)

        # Power slider
        self._power_slider = LockableSlider(
            min_value=0.0,
            max_value=100.0,
            color=self._color,
        )
        content_layout.addWidget(self._power_slider)

        outer_layout.addWidget(content)

        # Connect signals
        self._adapter.properties_changed.connect(self._on_properties_changed)
        self._enable_toggle.toggled.connect(self._on_toggle_changed)
        self._power_slider.inputReleased.connect(self._on_power_changed)

    def _on_properties_changed(self, props: dict[str, Any]) -> None:
        """Update UI from device properties."""
        if "wavelength" in props:
            wavelength = int(props["wavelength"])
            if self._wavelength != wavelength:
                self._wavelength = wavelength
                self._color = wavelength_to_hex(wavelength)
                self._power_slider.setColor(self._color)

                # Replace placeholder with wavelength chip
                if self._wavelength_chip is None:
                    self._chip_placeholder.hide()
                    self._wavelength_chip = WavelengthChip(wavelength)
                    self._header_layout.insertWidget(0, self._wavelength_chip)

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
        asyncio.create_task(self._adapter.call(command))
        log.debug("Laser %s: %s", self._adapter.uid, command)

    def _on_power_changed(self, value: float) -> None:
        """Handle power setpoint change from slider."""
        asyncio.create_task(self._adapter.set("power_setpoint_mw", value))
        log.debug("Laser %s: set power_setpoint_mw = %.1f", self._adapter.uid, value)

    def update_power_range(self, min_val: float, max_val: float) -> None:
        """Update the power slider range (call after fetching device interface)."""
        self._power_slider.setRange(min_val, max_val)
