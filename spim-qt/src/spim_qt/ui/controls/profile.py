"""Profile selector widget for switching acquisition profiles."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QWidget,
)

from spim_qt.ui.primitives.display import Label
from spim_qt.ui.primitives.input import Select
from spim_qt.ui.theme import Colors, Spacing

if TYPE_CHECKING:
    from spim_rig import SpimRig

log = logging.getLogger(__name__)


class ProfileSelector(QFrame):
    """Widget for selecting the active acquisition profile.

    Displays a dropdown with all available profiles and handles
    profile switching via the rig.

    Emits:
        profile_changed: Emitted when the profile is successfully changed.
            Carries the new profile ID.

    Usage:
        selector = ProfileSelector(rig)
        selector.profile_changed.connect(on_profile_changed)
        layout.addWidget(selector)
    """

    profile_changed = Signal(str)  # Emitted when profile changes

    def __init__(
        self,
        rig: SpimRig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rig = rig

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_MEDIUM};
                border-bottom: 1px solid {Colors.BORDER};
                border-radius: 0;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.SM)

        # Label
        layout.addWidget(Label("Profile", variant="section"))

        # Profile selector dropdown
        profiles = self._rig.available_profiles
        current = self._rig.active_profile_id

        self._select = Select(
            options=profiles,
            value=current,
        )
        layout.addWidget(self._select)

        # Profile description (if available)
        self._desc_label = Label("", variant="muted")
        self._desc_label.setWordWrap(True)
        layout.addWidget(self._desc_label)

        # Update description for current profile
        self._update_description(current)

    def _connect_signals(self) -> None:
        """Connect signals."""
        self._select.value_changed.connect(self._on_profile_selected)

    def _update_description(self, profile_id: str | None) -> None:
        """Update the description label for the given profile."""
        if not profile_id:
            self._desc_label.setText("")
            return

        profile = self._rig.config.profiles.get(profile_id)
        if profile:
            # Show label if different from ID, or description
            if profile.label and profile.label != profile_id:
                self._desc_label.setText(profile.label)
            elif profile.desc:
                self._desc_label.setText(profile.desc)
            else:
                # Show channel count
                num_channels = len(profile.channels)
                self._desc_label.setText(f"{num_channels} channel{'s' if num_channels != 1 else ''}")
        else:
            self._desc_label.setText("")

    def _on_profile_selected(self, profile_id: str) -> None:
        """Handle profile selection from dropdown."""
        if profile_id == self._rig.active_profile_id:
            return  # No change

        log.info("Switching profile to: %s", profile_id)
        asyncio.create_task(self._switch_profile(profile_id))

    async def _switch_profile(self, profile_id: str) -> None:
        """Switch to a new profile (async)."""
        try:
            await self._rig.set_active_profile(profile_id)
            self._update_description(profile_id)
            self.profile_changed.emit(profile_id)
            log.info("Profile switched to: %s", profile_id)
        except Exception:
            log.exception("Failed to switch profile")
            # Revert selection to current profile
            self._select.blockSignals(True)
            self._select.set_value(self._rig.active_profile_id)
            self._select.blockSignals(False)

    def refresh(self) -> None:
        """Refresh the selector to match current rig state."""
        current = self._rig.active_profile_id
        self._select.blockSignals(True)
        self._select.set_options(self._rig.available_profiles, current)
        self._select.blockSignals(False)
        self._update_description(current)
