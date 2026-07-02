"""The channels sidebar — the operational left panel for a launched instrument.

Header: a profile selector (drives :meth:`Instrument.set_active_profile`) and a Start/Stop Preview
toggle (drives :meth:`Instrument.start_preview` / :meth:`Instrument.stop_preview`). Body: one
:class:`ChannelSection` per channel of the active profile, each reusing the live device widgets
(camera + laser) bound to the ``DevicesStore`` adapters.

Sections are (re)built on the ``DevicesStore.ready`` signal and whenever the active profile changes;
the preview button tracks ``instrument.mode``. The panel owns its reactive subscriptions and detaches
them in :meth:`teardown` (the instrument outlives this window).
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget

from vxl.instrument import AcquisitionMode, Channel, ChannelConfig, Instrument
from vxl_qt.devices import DevicesStore
from vxl_qt.devices.widgets.camera import CameraControl
from vxl_qt.devices.widgets.laser import LaserControl
from vxl_qt.ui.kit import (
    Button,
    Color,
    Colors,
    ControlSize,
    Flex,
    Select,
    SelectOption,
    Separator,
    Spacing,
    Stretch,
    Text,
    vbox,
)
from vxlib import Teardown, display_name, fire_and_forget

log = logging.getLogger(__name__)


class ChannelSection(QWidget):
    """Live device controls (camera + laser) for one channel of the active profile."""

    def __init__(
        self, channel: Channel, config: ChannelConfig, devices: DevicesStore, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        layout = vbox(self, spacing=Spacing.MD, margins=(0, 0, 0, Spacing.MD))

        camera = devices.get_adapter(config.detection)
        if camera is None:
            raise ValueError(f"Channel '{channel.uid}': no adapter for detection device '{config.detection}'")

        label = (config.label or channel.uid).upper()
        color = Color.from_wavelength(config.emission) if config.emission else Colors.TEXT
        auto = Button.icon_btn("mdi.auto-fix", size=ControlSize.SM)
        auto.setToolTip("Auto-adjust levels")
        auto.clicked.connect(lambda: fire_and_forget(camera.call("auto_level"), log=log))
        layout.addWidget(Flex.hstack(Text.section(label, color=color), Stretch(), auto, spacing=Spacing.SM))

        layout.addWidget(CameraControl(camera))

        laser = devices.get_adapter(config.illumination)
        if laser is None:
            raise ValueError(f"Channel '{channel.uid}': no adapter for illumination device '{config.illumination}'")
        layout.addWidget(LaserControl(laser))


class ChannelsPanel(QWidget):
    """Operational sidebar: profile selector + preview toggle, with per-channel device controls."""

    def __init__(self, instrument: Instrument, devices: DevicesStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._instrument = instrument
        self._devices = devices
        self._unsubs: list[Teardown] = []

        self._profile_select = Select(size=ControlSize.LG)
        self._profile_select.value_changed.connect(self._on_profile_selected)

        self._preview_btn = Button.primary("Start Preview", size=ControlSize.LG)
        self._preview_btn.clicked.connect(self._on_preview_clicked)

        header = Flex.hstack(
            (self._profile_select, 1),
            self._preview_btn,
            spacing=Spacing.MD,
            padding=(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG),
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._channels_box = Flex.vstack(
            spacing=Spacing.LG,
            background=Colors.BG_DARK,
            padding=(Spacing.MD, Spacing.LG, Spacing.MD, Spacing.SM),
        )
        self._channels_box.add_stretch()
        scroll.setWidget(self._channels_box)

        layout = vbox(self)
        layout.addWidget(header)
        layout.addWidget(Separator())
        layout.addWidget(scroll, stretch=1)

        self._refresh_profiles()
        self._rebuild_sections()
        self._sync_preview_button(instrument.mode.value)

        self._devices.ready.connect(self._rebuild_sections)
        self._unsubs.append(instrument.active_profile_id.subscribe(self._on_active_profile))
        self._unsubs.append(instrument.mode.subscribe(self._sync_preview_button))

    def _refresh_profiles(self) -> None:
        """Populate the profile selector from the bench, selecting the active profile."""
        options: list[SelectOption] = []
        for pid, cfg in self._instrument.state.value.imaging.profiles.items():
            label = cfg.label or display_name(pid)
            options.append((pid, label, cfg.desc) if cfg.desc else (pid, label))
        active_id = self._instrument.active_profile_id.value
        self._profile_select.blockSignals(True)
        self._profile_select.set_options(options, active_id or None)
        self._profile_select.blockSignals(False)

    def _rebuild_sections(self) -> None:
        """Rebuild the channel sections for the active profile (no-op until devices are up)."""
        self._channels_box.clear()
        channels = self._instrument.active_channels
        if channels and self._devices.adapters:
            configs = self._instrument.state.value.imaging.channels
            for channel in channels.values():
                config = configs.get(channel.uid)
                if config is not None:
                    self._channels_box.add(ChannelSection(channel, config, self._devices))
        self._channels_box.add_stretch()

    def _on_active_profile(self, profile_id: str) -> None:
        """React to a profile switch: keep the selector in sync and rebuild the sections."""
        if profile_id:
            self._profile_select.blockSignals(True)
            self._profile_select.set_value(profile_id)
            self._profile_select.blockSignals(False)
        self._rebuild_sections()

    def _on_profile_selected(self, profile_id: str) -> None:
        if profile_id == self._instrument.active_profile_id.value:
            return
        fire_and_forget(self._instrument.set_active_profile(profile_id), log=log)

    def _on_preview_clicked(self) -> None:
        if self._instrument.mode.value == AcquisitionMode.PREVIEW:
            fire_and_forget(self._instrument.stop_preview(), log=log)
        else:
            fire_and_forget(self._instrument.start_preview(), log=log)

    def _sync_preview_button(self, mode: AcquisitionMode) -> None:
        previewing = mode == AcquisitionMode.PREVIEW
        self._preview_btn.setText("Stop Preview" if previewing else "Start Preview")
        self._preview_btn.fmt(Button.Fmt.danger() if previewing else Button.Fmt.primary())
        self._preview_btn.setEnabled(mode != AcquisitionMode.CAPTURE)  # engine busy during a capture

    def teardown(self) -> None:
        """Detach all subscriptions. Called when the control window closes."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        self._devices.ready.disconnect(self._rebuild_sections)
