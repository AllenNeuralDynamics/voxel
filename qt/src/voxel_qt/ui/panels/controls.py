import logging
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget

from voxel.camera.preview import PreviewCrop, PreviewFrame, PreviewLevels
from voxel.config import ChannelConfig
from voxel_qt.store import DevicesStore
from voxel_qt.ui.devices.camera import CameraControl
from voxel_qt.ui.devices.laser import LaserControl
from voxel_qt.ui.kit import (
    Box,
    Button,
    Color,
    Colors,
    ControlSize,
    Select,
    SelectOption,
    Separator,
    Size,
    Spacing,
    Stretch,
    Text,
    ToolButton,
    vbox,
)
from vxlib import display_name, fire_and_forget

log = logging.getLogger(__name__)
if TYPE_CHECKING:
    from voxel_qt.app import VoxelApp


class ChannelSection(QWidget):
    """Section for controlling devices in a single acquisition channel."""

    auto_levels_requested = Signal(str)  # channel_id

    def __init__(
        self,
        channel_id: str,
        channel_config: ChannelConfig,
        devices: DevicesStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._channel_id = channel_id
        self._config = channel_config
        self._devices = devices

        layout = vbox(self, spacing=Spacing.MD, margins=(0, 0, 0, Spacing.MD))

        # Section header - use wavelength color if available
        label_text = (channel_config.label or channel_id).upper()
        label_color = Color.from_wavelength(channel_config.emission) if channel_config.emission else Colors.TEXT
        auto_btn = Button.icon_btn("mdi.auto-fix", size=ControlSize.SM)
        auto_btn.setToolTip("Auto-adjust levels")
        auto_btn.clicked.connect(self._on_auto_clicked)
        header = Box.hstack(
            Text.section(label_text, color=label_color),
            auto_btn,
            padding=(Spacing.LG, 0, Spacing.XS, 0),
        )
        layout.addWidget(header)

        camera_adapter = self._devices.get_adapter(channel_config.detection)
        if not camera_adapter:
            raise ValueError(f"No camera adapter found for channel {channel_id}")
        self._camera_control = CameraControl(camera_adapter)
        layout.addWidget(self._camera_control)

        laser_adapter = self._devices.get_adapter(channel_config.illumination)
        if not laser_adapter:
            raise ValueError(f"No laser adapter found for channel {channel_id}")
        self._laser_control = LaserControl(laser_adapter)
        layout.addWidget(self._laser_control)

    @property
    def channel_id(self) -> str:
        """Get the channel ID."""
        return self._channel_id

    def _on_auto_clicked(self) -> None:
        """Handle auto-levels button click."""
        self.auto_levels_requested.emit(self._channel_id)


class ControlPanel(QWidget):
    """Left sidebar with header (profile selector, preview button) and channel sections (scrollable)."""

    profile_changed = Signal(str)
    preview_toggled = Signal(bool)

    def __init__(self, app: "VoxelApp", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._channel_sections: dict[str, ChannelSection] = {}
        self._previewing = False
        self._auto_leveled_channels: set[str] = set()

        self.setMinimumWidth(400)
        self.setMaximumWidth(600)

        # Profile selector
        self._profile_select = Select(size=ControlSize.LG)
        self._profile_select.value_changed.connect(self._on_profile_selected)

        # Preview button
        self._preview_btn = Button.primary("Start Preview", size=ControlSize.LG)
        self._preview_btn.clicked.connect(self._on_preview_clicked)

        # Header
        header = Box.hstack(
            (self._profile_select, 1),
            self._preview_btn,
            spacing=Spacing.MD,
            padding=(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG),
        )

        # Scrollable area for channel sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._channels_box = Box.vstack(
            spacing=Spacing.LG,
            background=Colors.BG_DARK,
            padding=(Spacing.MD, Spacing.LG, Spacing.MD, Spacing.SM),
        )
        self._channels_box.add_stretch()

        scroll.setWidget(self._channels_box)

        # Footer with connection status and exit button (same height as status bar)
        self._status_dot = Text.muted("●", color=Colors.TEXT_DISABLED)
        self._status_label = Text.muted("Connecting...")

        self._exit_btn = ToolButton("mdi.exit-to-app", color=Colors.TEXT_MUTED)
        self._exit_btn.setToolTip("Exit session")
        self._exit_btn.clicked.connect(self._on_exit_clicked)

        footer = Box.hstack(
            self._status_dot,
            self._status_label,
            Stretch(),
            self._exit_btn,
            spacing=Spacing.SM,
            padding=(Spacing.MD, 0, Spacing.MD, 0),
        )
        footer.setFixedHeight(Size.XL)

        # Main layout
        layout = vbox(self)
        layout.addWidget(header)
        layout.addWidget(Separator())
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(Separator())
        layout.addWidget(footer)

        # Connect to app signals
        self._app.devices_ready.connect(self._on_devices_ready)

        # Connect to preview store crop changes to notify rig
        self._app.preview.crop_changed.connect(self._on_crop_changed)

    def _build_profile_options(self) -> list[SelectOption]:
        """Build select options from rig profiles."""
        rig = self._app.rig
        if not rig:
            return []

        options: list[SelectOption] = []
        for profile_id in rig.available_profiles:
            profile = rig.config.profiles.get(profile_id)
            if profile:
                label = profile.label or display_name(profile_id)
                desc = profile.desc
                if desc:
                    options.append((profile_id, label, desc))
                else:
                    options.append((profile_id, label))
            else:
                options.append(profile_id)
        return options

    def _refresh_profile_select(self) -> None:
        """Refresh the profile selector from rig state."""
        rig = self._app.rig
        if not rig:
            return

        self._profile_select.blockSignals(True)
        self._profile_select.set_options(self._build_profile_options(), rig.active_profile_id)
        self._profile_select.blockSignals(False)

    def _on_devices_ready(self) -> None:
        """Initialize controls when devices are ready."""
        self._refresh_profile_select()
        self.rebuild_channel_sections()

    def rebuild_channel_sections(self) -> None:
        """Rebuild channel sections for the current profile."""
        rig = self._app.rig
        devices = self._app.devices

        if not rig or not devices:
            return

        # Clear existing sections
        self._channel_sections.clear()
        self._channels_box.clear()

        # Create new sections for active channels
        for channel_id, channel_config in rig.active_channels.items():
            section = ChannelSection(
                channel_id=channel_id,
                channel_config=channel_config,
                devices=devices,
            )
            section.auto_levels_requested.connect(self._on_auto_levels_requested)
            self._channel_sections[channel_id] = section
            self._channels_box.add(section)

        # Add stretch at bottom
        self._channels_box.add_stretch()

    def _on_profile_selected(self, profile_id: str) -> None:
        """Handle profile selection from dropdown."""
        rig = self._app.rig
        if not rig or profile_id == rig.active_profile_id:
            return

        log.info("Switching profile to: %s", profile_id)
        fire_and_forget(self._switch_profile(profile_id), log=log)

    async def _switch_profile(self, profile_id: str) -> None:
        """Switch to a new profile."""
        rig = self._app.rig
        if not rig:
            return

        try:
            await rig.set_active_profile(profile_id)
            self.profile_changed.emit(profile_id)
            self.rebuild_channel_sections()
            self._app.preview.clear_frames()
            self._auto_leveled_channels.clear()
            log.info("Profile switched to: %s", profile_id)
        except Exception:
            log.exception("Failed to switch profile")
            # Revert selection to current profile
            self._profile_select.blockSignals(True)
            self._profile_select.set_value(rig.active_profile_id)
            self._profile_select.blockSignals(False)

    def _on_crop_changed(self, x: float, y: float, k: float) -> None:
        """Handle crop changes from preview store - notify rig."""
        rig = self._app.rig
        if rig:
            crop = PreviewCrop(x=x, y=y, k=k)
            fire_and_forget(rig.update_preview_crop(crop), log=log)

    def _on_preview_clicked(self) -> None:
        """Toggle preview state."""
        self._previewing = not self._previewing
        if self._previewing:
            log.info("Starting preview")
            self._preview_btn.setText("Stop Preview")
            self._preview_btn.fmt(Button.Fmt.danger())
            fire_and_forget(self._start_preview(), log=log)
        else:
            log.info("Stopping preview")
            self._preview_btn.setText("Start Preview")
            self._preview_btn.fmt(Button.Fmt.primary())
            fire_and_forget(self._stop_preview(), log=log)
        self.preview_toggled.emit(self._previewing)

    async def _start_preview(self) -> None:
        """Start preview streaming."""
        self._auto_leveled_channels.clear()
        self._app.preview.clear_frames()
        rig = self._app.rig
        if rig:
            crop = self._app.preview.crop
            await rig.start_preview(self._on_frame, crop=crop)

    async def _stop_preview(self) -> None:
        """Stop preview streaming."""
        rig = self._app.rig
        if rig:
            await rig.stop_preview()

    async def _on_frame(self, channel: str, data: bytes) -> None:
        """Frame callback - decode and send to preview store."""
        frame = PreviewFrame.from_packed(data)
        image_data = self._decode_frame(frame.data)
        if image_data is None:
            return

        info = frame.info
        self._app.preview.set_frame(
            channel=channel,
            data=image_data,
            crop=info.crop,
            colormap=info.colormap,
            histogram=info.histogram,
        )

        # Auto-level on first frame with histogram
        if channel not in self._auto_leveled_channels and info.histogram is not None:
            self._auto_leveled_channels.add(channel)
            self._on_auto_levels_requested(channel)

    def _decode_frame(self, data: bytes) -> np.ndarray | None:
        """Decode compressed frame data to RGB numpy array."""
        qimage = QImage()
        if not qimage.loadFromData(data):
            return None
        if qimage.format() != QImage.Format.Format_RGB888:
            qimage = qimage.convertToFormat(QImage.Format.Format_RGB888)
        width = qimage.width()
        height = qimage.height()
        ptr = qimage.bits()
        return np.array(ptr, dtype=np.uint8).reshape((height, width, 3)).copy()

    def _on_auto_levels_requested(self, channel_id: str) -> None:
        """Handle auto-levels request from channel section."""
        histogram = self._app.preview.get_histogram(channel_id)
        if histogram is None:
            log.warning("No histogram available for channel %s", channel_id)
            return

        levels = PreviewLevels.from_histogram(histogram)
        log.info("Auto-levels for %s: min=%.3f, max=%.3f", channel_id, levels.min, levels.max)

        rig = self._app.rig
        if rig:
            fire_and_forget(rig.update_preview_levels({channel_id: levels}), log=log)

    def _on_exit_clicked(self) -> None:
        """Exit the active session."""
        fire_and_forget(self._app.close_session(), log=log)

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
