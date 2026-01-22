"""Camera device control widget."""

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
from spim_qt.ui.primitives.input import LockableSlider, Select
from spim_qt.ui.theme import Colors, Spacing

if TYPE_CHECKING:
    from spim_qt.devices import DevicesManager

log = logging.getLogger(__name__)


class CameraControl(QWidget):
    """Camera device control widget.

    Displays:
    - Row 1: Camera label + frame info
    - Row 2: Exposure slider
    - Row 3: Format + Binning selectors (inline)

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

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, Spacing.XS, 0, Spacing.XS)
        layout.setSpacing(Spacing.XS)

        # Row 1: Camera label + frame info
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(Spacing.SM)

        row1.addWidget(Label("Camera", variant="default", color=Colors.TEXT))

        row1.addStretch()

        self._frame_info_label = Label("--", variant="value", color=Colors.TEXT_MUTED)
        row1.addWidget(self._frame_info_label)

        layout.addLayout(row1)

        # Row 2: Exposure slider
        self._exposure_slider = LockableSlider(
            min_value=0.1,
            max_value=100.0,
            color=Colors.ACCENT,
        )
        layout.addWidget(self._exposure_slider)

        # Row 3: Format + Binning inline
        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(Spacing.MD)

        row3.addWidget(Label("Format", variant="muted"))

        self._format_select = Select(options=["Mono8", "Mono16"])
        row3.addWidget(self._format_select)

        row3.addSpacing(Spacing.SM)

        row3.addWidget(Label("Binning", variant="muted"))

        self._binning_select = Select(
            options=[1, 2, 4],
            format_option=lambda x: f"{x}x{x}",
        )
        row3.addWidget(self._binning_select)

        row3.addStretch()

        layout.addLayout(row3)

    def _connect_signals(self) -> None:
        """Connect to device adapter signals."""
        adapter = self._devices.get_adapter(self._device_id)
        if adapter:
            adapter.properties_changed.connect(self._on_properties_changed)

        # Connect UI signals
        self._exposure_slider.inputReleased.connect(self._on_exposure_changed)
        self._format_select.value_changed.connect(self._on_format_changed)
        self._binning_select.value_changed.connect(self._on_binning_changed)

    def _on_properties_changed(self, props: dict[str, Any]) -> None:
        """Update UI from device properties."""
        # Exposure time
        if "exposure_time_ms" in props:
            exposure = float(props["exposure_time_ms"])
            self._exposure_slider.setTarget(exposure)
            self._exposure_slider.setActual(exposure)

        # Pixel format
        if "pixel_format" in props:
            fmt = props["pixel_format"]
            self._format_select.blockSignals(True)
            self._format_select.set_value(fmt)
            self._format_select.blockSignals(False)

        # Binning
        if "binning" in props:
            binning = props["binning"]
            self._binning_select.blockSignals(True)
            self._binning_select.set_value(binning)
            self._binning_select.blockSignals(False)

        # Frame size + fps info
        info_parts = []
        if "frame_size_px" in props:
            size = props["frame_size_px"]
            if isinstance(size, (list, tuple)) and len(size) == 2:
                info_parts.append(f"{size[0]}x{size[1]}")

        if "stream_info" in props:
            info = props["stream_info"]
            if isinstance(info, dict):
                fps = info.get("frame_rate_fps", 0)
                info_parts.append(f"{float(fps):.1f} fps")
        elif "frame_rate_hz" in props:
            fps = float(props["frame_rate_hz"])
            info_parts.append(f"{fps:.1f} fps")

        if info_parts:
            self._frame_info_label.setText(" | ".join(info_parts))

    def _on_exposure_changed(self, value: float) -> None:
        """Handle exposure time change."""
        adapter = self._devices.get_adapter(self._device_id)
        if adapter:
            asyncio.create_task(adapter.set("exposure_time_ms", value))
            log.debug("Camera %s: set exposure_time_ms = %.2f", self._device_id, value)

    def _on_format_changed(self, value: Any) -> None:
        """Handle pixel format change."""
        adapter = self._devices.get_adapter(self._device_id)
        if adapter:
            asyncio.create_task(adapter.set("pixel_format", value))
            log.debug("Camera %s: set pixel_format = %s", self._device_id, value)

    def _on_binning_changed(self, value: Any) -> None:
        """Handle binning change."""
        adapter = self._devices.get_adapter(self._device_id)
        if adapter:
            asyncio.create_task(adapter.set("binning", value))
            log.debug("Camera %s: set binning = %s", self._device_id, value)

    def update_exposure_range(self, min_val: float, max_val: float) -> None:
        """Update the exposure slider range."""
        self._exposure_slider.setRange(min_val, max_val)

    def update_format_options(self, options: list[str]) -> None:
        """Update pixel format options."""
        current = self._format_select.get_value()
        self._format_select.set_options(options, current)

    def update_binning_options(self, options: list[int]) -> None:
        """Update binning options."""
        current = self._binning_select.get_value()
        self._binning_select.set_options(options, current)
