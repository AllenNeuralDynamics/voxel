"""Channel section widget combining device controls for a single channel."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

from spim_qt.ui.controls.camera import CameraControl
from spim_qt.ui.controls.laser import LaserControl
from spim_qt.ui.primitives.display import Label
from spim_qt.ui.theme import Colors, Spacing

if TYPE_CHECKING:
    from spim_rig.config import ChannelConfig

    from spim_qt.devices import DevicesManager

log = logging.getLogger(__name__)


class ChannelSection(QWidget):
    """Section for controlling devices in a single acquisition channel."""

    def __init__(
        self,
        channel_id: str,
        channel_config: ChannelConfig,
        devices: DevicesManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._channel_id = channel_id
        self._config = channel_config
        self._devices = devices

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        # Section header
        label_text = (channel_config.label or channel_id).upper()
        self._label = Label(label_text, variant="section", color=Colors.TEXT)
        self._label.setStyleSheet(
            self._label.styleSheet() + f"padding-bottom: {Spacing.XS}px; border-bottom: 1px solid {Colors.BORDER};"
        )
        layout.addWidget(self._label)

        # Illumination control (laser)
        self._laser_control: LaserControl | None = None
        if channel_config.illumination:
            adapter = devices.get_adapter(channel_config.illumination)
            if adapter:
                self._laser_control = LaserControl(adapter)
                layout.addWidget(self._laser_control)

        # Detection control (camera)
        self._camera_control: CameraControl | None = None
        if channel_config.detection:
            adapter = devices.get_adapter(channel_config.detection)
            if adapter:
                self._camera_control = CameraControl(adapter)
                layout.addWidget(self._camera_control)

    @property
    def channel_id(self) -> str:
        """Get the channel ID."""
        return self._channel_id

    @property
    def laser_control(self) -> LaserControl | None:
        """Get the laser control widget, if any."""
        return self._laser_control

    @property
    def camera_control(self) -> CameraControl | None:
        """Get the camera control widget, if any."""
        return self._camera_control
