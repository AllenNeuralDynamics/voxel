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

from spim_qt.ui.primitives.containers import CardDark
from spim_qt.ui.primitives.display import Label
from spim_qt.ui.primitives.input import LockableSlider, Select
from spim_qt.ui.theme import BorderRadius, Colors, Spacing

if TYPE_CHECKING:
    from spim_qt.handle import DeviceHandleQt

log = logging.getLogger(__name__)


class CameraControl(QWidget):
    """Camera device control widget.

    Displays:
    - Row 1: Camera label + frame info
    - Row 2: Exposure slider
    - Row 3: Format + Binning selectors (inline)

    Wrapped in a CardDark container.

    Args:
        adapter: DeviceHandleQt wrapping a camera device.
        parent: Parent widget.

    Example (integrated with spim-qt):
        adapter = devices_manager.get_adapter("camera_1")
        widget = CameraControl(adapter)

    Example (standalone):
        from spim_drivers.cameras.simulated import SimulatedCamera
        from pyrig import create_local_handle
        from spim_qt.handle import DeviceHandleQt

        device = SimulatedCamera(uid="cam")
        handle = create_local_handle(device)
        adapter = DeviceHandleQt(handle)
        await adapter.start()
        widget = CameraControl(adapter)
    """

    def __init__(
        self,
        adapter: DeviceHandleQt,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._adapter = adapter

        # Outer layout
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Content container
        content = CardDark(border_radius=BorderRadius.LG)
        existing_layout = content.layout()
        assert isinstance(existing_layout, QVBoxLayout)
        content_layout = existing_layout
        content_layout.setSpacing(Spacing.XS)

        # Row 1: Camera label + frame info
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(Spacing.SM)

        row1.addWidget(Label("Camera", variant="default", color=Colors.TEXT))
        row1.addStretch()

        self._frame_info_label = Label("--", variant="value", color=Colors.TEXT_MUTED)
        row1.addWidget(self._frame_info_label)

        content_layout.addLayout(row1)

        # Row 2: Exposure slider
        self._exposure_slider = LockableSlider(
            min_value=0.1,
            max_value=100.0,
            color=Colors.ACCENT,
        )
        content_layout.addWidget(self._exposure_slider)

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

        content_layout.addLayout(row3)

        outer_layout.addWidget(content)

        # Connect signals
        self._adapter.properties_changed.connect(self._on_properties_changed)
        self._exposure_slider.inputReleased.connect(self._on_exposure_changed)
        self._format_select.value_changed.connect(self._on_format_changed)
        self._binning_select.value_changed.connect(self._on_binning_changed)

    def _on_properties_changed(self, props: dict[str, Any]) -> None:
        """Update UI from device properties."""
        if "exposure_time_ms" in props:
            exposure = float(props["exposure_time_ms"])
            self._exposure_slider.setTarget(exposure)
            self._exposure_slider.setActual(exposure)

        if "pixel_format" in props:
            fmt = props["pixel_format"]
            self._format_select.blockSignals(True)
            self._format_select.set_value(fmt)
            self._format_select.blockSignals(False)

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
        asyncio.create_task(self._adapter.set("exposure_time_ms", value))
        log.debug("Camera %s: set exposure_time_ms = %.2f", self._adapter.uid, value)

    def _on_format_changed(self, value: Any) -> None:
        """Handle pixel format change."""
        asyncio.create_task(self._adapter.set("pixel_format", value))
        log.debug("Camera %s: set pixel_format = %s", self._adapter.uid, value)

    def _on_binning_changed(self, value: Any) -> None:
        """Handle binning change."""
        asyncio.create_task(self._adapter.set("binning", value))
        log.debug("Camera %s: set binning = %s", self._adapter.uid, value)

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
