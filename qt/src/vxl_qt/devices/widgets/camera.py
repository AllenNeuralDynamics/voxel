"""Camera device control widget."""

import logging
from typing import Any

from PySide6.QtWidgets import QVBoxLayout, QWidget

from vxl_qt.devices.adapter import DeviceHandleQt
from vxl_qt.devices.bind import bind_select, bind_slider_spinbox
from vxl_qt.ui.kit import (
    Accordion,
    Colors,
    ControlSize,
    Field,
    Flex,
    GridFormBuilder,
    Select,
    SliderSpinBox,
    Spacing,
    SpinBox,
    Stretch,
    Text,
)
from vxlib import fire_and_forget

log = logging.getLogger(__name__)


class CameraControl(QWidget):
    """Camera device control widget.

    Displays:
    - Header: Camera label + frame info
    - Exposure: label + value + slider
    - Format + Binning selectors (inline)
    - Frame region: Offset X/Y + Size W/H spinboxes (inline)
    - Accordion "Sensor Info": readonly sensor/pixel/area info
    - Accordion "Stream Info": data rate, dropped frames, etc.

    Wrapped in a CardDark container.

    Args:
        adapter: DeviceHandleQt wrapping a camera device.
        parent: Parent widget.
    """

    def __init__(self, adapter: DeviceHandleQt, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._adapter = adapter

        # Header
        self._frame_info_label = Text.value("--", color=Colors.TEXT_MUTED)

        # Exposure control
        self._exposure = SliderSpinBox(
            minimum=0.1, maximum=100.0, value=0.1, decimals=2, step=0.1, show_lock=True, size=ControlSize.SM
        )

        # Format/Binning — options are populated from the device's own enumerated values (see
        # _load_options), so this works for any camera; display_fmt is only the label, not the sent value.
        self._format_select = Select(display_fmt=lambda fmt: str(fmt).title())
        self._binning_select = Select(display_fmt=lambda factor: f"{factor}x{factor}")

        # Frame region spinboxes
        self._offset_x = SpinBox(value=0, min_val=0, max_val=10000, step=1)
        self._offset_y = SpinBox(value=0, min_val=0, max_val=10000, step=1)
        self._size_w = SpinBox(value=1024, min_val=1, max_val=10000, step=1)
        self._size_h = SpinBox(value=1024, min_val=1, max_val=10000, step=1)

        # Sensor Info accordion (readonly)
        self._sensor_info_accordion = Accordion("Frame Area", summary_value="-- x -- mm")
        self._frame_size_value = Text.muted("-- x -- px")
        self._frame_size_mb_value = Text.muted("-- MB")
        self._sensor_size_value = Text.muted("-- x -- px")
        self._pixel_size_value = Text.muted("-- x -- µm")

        # Stream Info accordion
        self._stream_info_accordion = Accordion("Stream Info", summary_value="-- fps")
        self._data_rate_value = Text.muted("-- MB/s")
        self._dropped_value = Text.muted("0")
        self._frame_idx_value = Text.muted("--")

        self._configure_layout()
        self._connect_signals()

    def _configure_layout(self) -> None:
        """Configure the widget layout."""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Header row
        header = Flex.hstack(Text.heading("Camera"), Stretch(), self._frame_info_label)

        # Form: Exposure, Format, Binning, Offset, Size
        form = (
            GridFormBuilder(columns=2)
            .row(Field("Exposure", self._exposure, span=2))
            .row(Field("Format", self._format_select), Field("Binning", self._binning_select))
            .row(Field("Offset X", self._offset_x), Field("Offset Y", self._offset_y))
            .row(Field("Width", self._size_w), Field("Height", self._size_h))
            .build()
        )

        # Sensor Info accordion
        sensor_layout = self._sensor_info_accordion.content_layout
        sensor_layout.addWidget(Flex.hstack(Text("Frame Size"), Stretch(), self._frame_size_value))
        sensor_layout.addWidget(Flex.hstack(Stretch(), self._frame_size_mb_value))
        sensor_layout.addWidget(Flex.hstack(Text("Pixel Size"), Stretch(), self._pixel_size_value))
        sensor_layout.addWidget(Flex.hstack(Text("Sensor Size"), Stretch(), self._sensor_size_value))

        # Stream Info accordion
        stream_layout = self._stream_info_accordion.content_layout
        stream_layout.addWidget(Flex.hstack(Text("Data Rate"), Stretch(), self._data_rate_value))
        stream_layout.addWidget(Flex.hstack(Text("Dropped Frames"), Stretch(), self._dropped_value))
        stream_layout.addWidget(Flex.hstack(Text("Frame Index"), Stretch(), self._frame_idx_value))

        # Card container with all content
        content = Flex.card(
            header,
            form,
            self._sensor_info_accordion,
            self._stream_info_accordion,
            spacing=Spacing.MD,
        )
        outer_layout.addWidget(content)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self._adapter.properties_changed.connect(self._on_properties_changed)

        # Exposure is a deliminated numeric: bind range + live value + edits from the device.
        bind_slider_spinbox(self._exposure, self._adapter, "exposure_time_ms")

        # Format/binning are enumerated device properties: bind options + value from the device.
        bind_select(self._format_select, self._adapter, "pixel_format")
        bind_select(self._binning_select, self._adapter, "binning")

        # ROI spinboxes
        self._offset_x.valueChanged.connect(self._on_roi_changed)
        self._offset_y.valueChanged.connect(self._on_roi_changed)
        self._size_w.valueChanged.connect(self._on_roi_changed)
        self._size_h.valueChanged.connect(self._on_roi_changed)

        # Request initial property values
        self._adapter.request_initial_properties()

    def _on_properties_changed(self, props: dict[str, Any]) -> None:
        """Update UI from device properties."""
        self._update_frame_info(props)
        self._update_sensor_info(props)
        self._update_roi(props)
        self._update_stream_info(props)

    def _update_frame_info(self, props: dict[str, Any]) -> None:
        """Update frame info label in header."""
        info_parts = []
        if "frame_size_px" in props:
            size = props["frame_size_px"]
            if isinstance(size, dict):
                info_parts.append(f"{size.get('x', 0)}x{size.get('y', 0)}")
            elif isinstance(size, (list, tuple)) and len(size) == 2:
                info_parts.append(f"{size[0]}x{size[1]}")

        if "stream_info" in props:
            info = props["stream_info"]
            if isinstance(info, dict):
                fps = info.get("frame_rate_fps", 0)
                info_parts.append(f"{float(fps):.1f} fps")
        elif "frame_rate_hz" in props:
            info_parts.append(f"{float(props['frame_rate_hz']):.1f} fps")

        if info_parts:
            self._frame_info_label.setText(" | ".join(info_parts))

    def _update_sensor_info(self, props: dict[str, Any]) -> None:
        """Update sensor info accordion rows."""
        if "frame_size_px" in props:
            size = props["frame_size_px"]
            if isinstance(size, dict):
                self._frame_size_value.setText(f"{size.get('x', 0)} x {size.get('y', 0)} px")
            elif isinstance(size, (list, tuple)) and len(size) == 2:
                self._frame_size_value.setText(f"{size[0]} x {size[1]} px")

        if "frame_size_mb" in props:
            self._frame_size_mb_value.setText(f"{float(props['frame_size_mb']):.2f} MB")

        if "sensor_size_px" in props:
            size = props["sensor_size_px"]
            if isinstance(size, dict):
                self._sensor_size_value.setText(f"{size.get('x', 0)} x {size.get('y', 0)} px")
            elif isinstance(size, (list, tuple)) and len(size) == 2:
                self._sensor_size_value.setText(f"{size[0]} x {size[1]} px")

        if "pixel_size_um" in props:
            size = props["pixel_size_um"]
            if isinstance(size, dict):
                self._pixel_size_value.setText(f"{size.get('x', 0):.2f} x {size.get('y', 0):.2f} µm")
            elif isinstance(size, (list, tuple)) and len(size) == 2:
                self._pixel_size_value.setText(f"{size[0]:.2f} x {size[1]:.2f} µm")

        if "frame_area_um" in props:
            area = props["frame_area_um"]
            if isinstance(area, dict):
                x_mm, y_mm = area.get("x", 0) / 1000, area.get("y", 0) / 1000
                self._sensor_info_accordion.set_summary(f"{x_mm:.2f} x {y_mm:.2f} mm")
            elif isinstance(area, (list, tuple)) and len(area) == 2:
                self._sensor_info_accordion.set_summary(f"{area[0] / 1000:.2f} x {area[1] / 1000:.2f} mm")

    def _update_roi(self, props: dict[str, Any]) -> None:
        """Update ROI spinboxes from roi values and roi_grid constraints."""
        # Update constraints from roi_grid
        if "roi_grid" in props:
            grid = props["roi_grid"]
            if isinstance(grid, dict):
                h = grid.get("h", {})
                v = grid.get("v", {})
                if h:
                    self._size_w.blockSignals(True)
                    self._size_w.setRange(h.get("min", 1), h.get("max", 99999))
                    self._size_w.setSingleStep(h.get("step", 1))
                    self._size_w.blockSignals(False)
                    self._offset_x.blockSignals(True)
                    self._offset_x.setSingleStep(h.get("step", 1))
                    self._offset_x.blockSignals(False)
                if v:
                    self._size_h.blockSignals(True)
                    self._size_h.setRange(v.get("min", 1), v.get("max", 99999))
                    self._size_h.setSingleStep(v.get("step", 1))
                    self._size_h.blockSignals(False)
                    self._offset_y.blockSignals(True)
                    self._offset_y.setSingleStep(v.get("step", 1))
                    self._offset_y.blockSignals(False)

        # Update values from roi
        if "roi" in props:
            roi = props["roi"]
            if isinstance(roi, dict):
                for spinbox, key in [
                    (self._offset_x, "x"),
                    (self._offset_y, "y"),
                    (self._size_w, "w"),
                    (self._size_h, "h"),
                ]:
                    if key in roi:
                        spinbox.blockSignals(True)
                        spinbox.setValue(roi[key])
                        spinbox.blockSignals(False)

    def _update_stream_info(self, props: dict[str, Any]) -> None:
        """Update stream info accordion."""
        if "stream_info" not in props:
            return

        info = props["stream_info"]
        if not info or not isinstance(info, dict):
            return

        fps = info.get("frame_rate_fps", 0)
        self._stream_info_accordion.set_summary(f"{float(fps):.2f} fps")

        self._data_rate_value.setText(f"{float(info.get('data_rate_mbs', 0)):.1f} MB/s")
        self._dropped_value.setText(str(info.get("dropped_frames", 0)))
        self._frame_idx_value.setText(str(info.get("frame_index", "--")))

    def _on_roi_changed(self) -> None:
        """Called when any ROI spinbox changes."""
        fire_and_forget(
            self._adapter.call(
                "update_roi",
                roi={
                    "x": self._offset_x.value(),
                    "y": self._offset_y.value(),
                    "w": self._size_w.value(),
                    "h": self._size_h.value(),
                },
            ),
            log=log,
        )
