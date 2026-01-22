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

from spim_qt.ui.primitives.display import Label
from spim_qt.ui.primitives.input import LockableSlider, Toggle
from spim_qt.ui.theme import Colors, Spacing

if TYPE_CHECKING:
    from spim_qt.devices import DevicesManager

log = logging.getLogger(__name__)


def wavelength_to_color(wavelength_nm: int | float) -> str:
    """Convert wavelength (nm) to approximate RGB hex color.

    Based on Dan Bruton's algorithm for visible spectrum colors.
    """
    wl = float(wavelength_nm)

    if 380 <= wl < 440:
        r = -(wl - 440) / (440 - 380)
        g = 0.0
        b = 1.0
    elif 440 <= wl < 490:
        r = 0.0
        g = (wl - 440) / (490 - 440)
        b = 1.0
    elif 490 <= wl < 510:
        r = 0.0
        g = 1.0
        b = -(wl - 510) / (510 - 490)
    elif 510 <= wl < 580:
        r = (wl - 510) / (580 - 510)
        g = 1.0
        b = 0.0
    elif 580 <= wl < 645:
        r = 1.0
        g = -(wl - 645) / (645 - 580)
        b = 0.0
    elif 645 <= wl <= 780:
        r = 1.0
        g = 0.0
        b = 0.0
    else:
        # Outside visible range - gray
        r = g = b = 0.5

    # Intensity adjustment at edges
    if 380 <= wl < 420:
        factor = 0.3 + 0.7 * (wl - 380) / (420 - 380)
    elif 645 < wl <= 780:
        factor = 0.3 + 0.7 * (780 - wl) / (780 - 645)
    else:
        factor = 1.0

    r = int(r * factor * 255)
    g = int(g * factor * 255)
    b = int(b * factor * 255)

    return f"#{r:02x}{g:02x}{b:02x}"


class LaserControl(QWidget):
    """Laser device control widget.

    Displays:
    - Row 1: Wavelength label + enable toggle + power readout
    - Row 2: Power setpoint slider

    Args:
        compact: If True, uses minimal styling for embedding in other widgets.
    """

    def __init__(
        self,
        device_id: str,
        devices: DevicesManager,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._device_id = device_id
        self._devices = devices
        self._compact = compact
        self._wavelength: int | None = None
        self._color = Colors.ACCENT

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, Spacing.XS, 0, Spacing.XS)
        layout.setSpacing(Spacing.XS)

        # Row 1: wavelength + toggle + power readout
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(Spacing.SM)

        self._wavelength_label = Label("Laser", variant="default", color=Colors.TEXT)
        row1.addWidget(self._wavelength_label)

        row1.addStretch()

        self._power_label = Label("-- mW", variant="value", color=Colors.TEXT_MUTED)
        row1.addWidget(self._power_label)

        self._enable_toggle = Toggle()
        self._enable_toggle.setToolTip("Enable/disable laser emission")
        row1.addWidget(self._enable_toggle)

        layout.addLayout(row1)

        # Row 2: Power slider
        self._power_slider = LockableSlider(
            min_value=0.0,
            max_value=100.0,
            color=self._color,
        )
        layout.addWidget(self._power_slider)

    def _connect_signals(self) -> None:
        """Connect to device adapter signals."""
        adapter = self._devices.get_adapter(self._device_id)
        if adapter:
            adapter.properties_changed.connect(self._on_properties_changed)

        # Connect UI signals
        self._enable_toggle.toggled.connect(self._on_toggle_changed)
        self._power_slider.inputReleased.connect(self._on_power_changed)

    def _on_properties_changed(self, props: dict[str, Any]) -> None:
        """Update UI from device properties."""
        # Wavelength (usually static)
        if "wavelength" in props:
            self._wavelength = int(props["wavelength"])
            self._wavelength_label.setText(f"{self._wavelength} nm Laser")
            self._color = wavelength_to_color(self._wavelength)
            self._power_slider.setColor(self._color)

        # Enable state
        if "is_enabled" in props:
            is_enabled = bool(props["is_enabled"])
            self._enable_toggle.blockSignals(True)
            self._enable_toggle.setChecked(is_enabled)
            self._enable_toggle.blockSignals(False)

        # Power setpoint (target value for slider)
        if "power_setpoint_mw" in props:
            setpoint = float(props["power_setpoint_mw"])
            self._power_slider.setTarget(setpoint)

        # Actual power (progress bar + label)
        if "power_mw" in props:
            power = float(props["power_mw"])
            self._power_slider.setActual(power)
            self._power_label.setText(f"{power:.1f} mW")

    def _on_toggle_changed(self, checked: bool) -> None:
        """Handle enable toggle change."""
        adapter = self._devices.get_adapter(self._device_id)
        if adapter:
            command = "enable" if checked else "disable"
            asyncio.create_task(adapter.call(command))
            log.debug("Laser %s: %s", self._device_id, command)

    def _on_power_changed(self, value: float) -> None:
        """Handle power setpoint change from slider."""
        adapter = self._devices.get_adapter(self._device_id)
        if adapter:
            asyncio.create_task(adapter.set("power_setpoint_mw", value))
            log.debug("Laser %s: set power_setpoint_mw = %.1f", self._device_id, value)

    def update_power_range(self, min_val: float, max_val: float) -> None:
        """Update the power slider range (call after fetching device interface)."""
        self._power_slider.setRange(min_val, max_val)
