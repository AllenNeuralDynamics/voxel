"""Device management for SPIM Qt application.

This module provides centralized management of device handles and their Qt adapters,
enabling reactive UI updates when device properties change.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal

from spim_qt.handle import DeviceHandleQt

if TYPE_CHECKING:
    from pyrig import DeviceHandle
    from spim_rig import Session


log = logging.getLogger(__name__)


class DevicesManager(QObject):
    """Manages device handles and their Qt adapters for the UI.

    This class creates DeviceHandleQt adapters for all rig devices and provides
    convenient access methods for widgets to query device state and subscribe
    to property updates.

    Usage:
        manager = DevicesManager(session)
        await manager.start()

        # Get adapter for a device
        adapter = manager.get_adapter("laser_488")
        adapter.properties_changed.connect(self._on_laser_props)

        # Or use convenience methods
        value = manager.get_property("laser_488", "power_mw")
    """

    # Signals
    device_added = Signal(str)  # device_id
    device_removed = Signal(str)  # device_id
    ready = Signal()  # All adapters started

    def __init__(self, session: Session, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._adapters: dict[str, DeviceHandleQt] = {}
        self._started = False

        # Cache for property values (updated by adapters)
        self._property_cache: dict[str, dict[str, Any]] = {}

    @property
    def session(self) -> Session:
        """Access the underlying session."""
        return self._session

    @property
    def rig(self):
        """Access the underlying rig."""
        return self._session.rig

    @property
    def adapters(self) -> dict[str, DeviceHandleQt]:
        """All device adapters by device ID."""
        return self._adapters

    async def start(self) -> None:
        """Create and start adapters for all rig handles."""
        if self._started:
            log.warning("DevicesManager already started")
            return

        log.info("Starting DevicesManager with %d devices", len(self.rig.handles))

        for uid, handle in self.rig.handles.items():
            adapter = DeviceHandleQt(handle, parent=self)
            adapter.properties_changed.connect(lambda props, uid=uid: self._on_properties(uid, props))

            await adapter.start()
            self._adapters[uid] = adapter
            self._property_cache[uid] = {}
            self.device_added.emit(uid)

        self._started = True
        self.ready.emit()
        log.info("DevicesManager ready with %d adapters", len(self._adapters))

    async def stop(self) -> None:
        """Stop all adapters."""
        if not self._started:
            return

        log.info("Stopping DevicesManager")

        for uid, adapter in self._adapters.items():
            await adapter.stop()
            self.device_removed.emit(uid)

        self._adapters.clear()
        self._property_cache.clear()
        self._started = False

    def _on_properties(self, device_id: str, props: dict[str, Any]) -> None:
        """Handle property update from an adapter."""
        if device_id in self._property_cache:
            self._property_cache[device_id].update(props)

    # ==================== Access Methods ====================

    def get_adapter(self, device_id: str) -> DeviceHandleQt | None:
        """Get the Qt adapter for a device.

        Args:
            device_id: Device unique identifier

        Returns:
            DeviceHandleQt adapter, or None if device not found
        """
        return self._adapters.get(device_id)

    def get_handle(self, device_id: str) -> DeviceHandle | None:
        """Get the underlying DeviceHandle for a device.

        Args:
            device_id: Device unique identifier

        Returns:
            DeviceHandle, or None if device not found
        """
        adapter = self._adapters.get(device_id)
        return adapter.handle if adapter else None

    def get_property(self, device_id: str, prop_name: str) -> Any | None:
        """Get a cached property value.

        Note: This returns the last known value from property streaming.
        For the latest value, use adapter.get(prop_name) which is async.

        Args:
            device_id: Device unique identifier
            prop_name: Property name

        Returns:
            Property value, or None if not found/not cached
        """
        device_cache = self._property_cache.get(device_id)
        if device_cache is None:
            return None
        return device_cache.get(prop_name)

    def get_properties(self, device_id: str) -> dict[str, Any]:
        """Get all cached properties for a device.

        Args:
            device_id: Device unique identifier

        Returns:
            Dict of property name -> value, or empty dict if device not found
        """
        return self._property_cache.get(device_id, {}).copy()

    # ==================== Device Type Shortcuts ====================

    def get_lasers(self) -> dict[str, DeviceHandleQt]:
        """Get all laser device adapters."""
        return {uid: self._adapters[uid] for uid in self.rig.lasers if uid in self._adapters}

    def get_cameras(self) -> dict[str, DeviceHandleQt]:
        """Get all camera device adapters."""
        return {uid: self._adapters[uid] for uid in self.rig.cameras if uid in self._adapters}

    def get_filter_wheels(self) -> dict[str, DeviceHandleQt]:
        """Get all filter wheel device adapters."""
        return {uid: self._adapters[uid] for uid in self.rig.fws if uid in self._adapters}

    def get_stage_axes(self) -> dict[str, DeviceHandleQt]:
        """Get stage axis adapters (x, y, z)."""
        stage_ids = [
            self.rig.config.stage.x,
            self.rig.config.stage.y,
            self.rig.config.stage.z,
        ]
        return {uid: self._adapters[uid] for uid in stage_ids if uid in self._adapters}
