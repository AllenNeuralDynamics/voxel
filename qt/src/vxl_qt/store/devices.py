"""Device state store for Voxel application.

This module provides centralized management of device handles and their Qt adapters,
enabling reactive UI updates when device properties change.
"""

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal

from rigup import DeviceHandle
from vxl_qt.handle import DeviceHandleQt

if TYPE_CHECKING:
    from vxl import Session

log = logging.getLogger(__name__)


class DevicesStore(QObject):
    """Manages device handles and their Qt adapters for the UI.

    This class creates DeviceHandleQt adapters for all rig devices and provides
    convenient access methods for widgets to query device state and subscribe
    to property updates.

    Usage:
        store = DevicesStore()
        await store.start(session)

        # Get adapter for a device
        adapter = store.get_adapter("laser_488")
        adapter.properties_changed.connect(self._on_laser_props)

        # Or use convenience methods
        value = store.get_property("laser_488", "power_mw")
    """

    device_added = Signal(str)  # device_id
    device_removed = Signal(str)  # device_id
    ready = Signal()  # All adapters started

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session: Session | None = None
        self._adapters: dict[str, DeviceHandleQt] = {}
        self._started = False
        self._property_cache: dict[str, dict[str, Any]] = {}

    @property
    def session(self) -> "Session | None":
        """Access the underlying session."""
        return self._session

    @property
    def rig(self):
        """Access the underlying rig."""
        if self._session is None:
            return None
        return self._session.rig

    @property
    def adapters(self) -> dict[str, DeviceHandleQt]:
        """All device adapters by device ID."""
        return self._adapters

    async def start(self, session: "Session") -> None:
        """Create and start adapters for all rig handles."""
        if self._started:
            log.warning("DevicesStore already started")
            return

        self._session = session
        rig = session.rig
        log.info("Starting DevicesStore with %d devices", len(rig.handles))

        for uid, handle in rig.handles.items():
            adapter = DeviceHandleQt(handle, parent=self)
            adapter.properties_changed.connect(lambda props, uid=uid: self._on_properties(uid, props))

            await adapter.start()
            self._adapters[uid] = adapter
            self._property_cache[uid] = {}
            self.device_added.emit(uid)

        self._started = True
        self.ready.emit()
        log.info("DevicesStore ready with %d adapters", len(self._adapters))

    async def stop(self) -> None:
        """Stop all adapters."""
        if not self._started:
            return

        log.info("Stopping DevicesStore")

        for uid, adapter in self._adapters.items():
            await adapter.stop()
            self.device_removed.emit(uid)

        self._adapters.clear()
        self._property_cache.clear()
        self._session = None
        self._started = False

    def _on_properties(self, device_id: str, props: dict[str, Any]) -> None:
        """Handle property update from an adapter."""
        if device_id in self._property_cache:
            self._property_cache[device_id].update(props)

    def get_adapter(self, device_id: str) -> DeviceHandleQt | None:
        """Get the Qt adapter for a device."""
        return self._adapters.get(device_id)

    def get_handle(self, device_id: str) -> DeviceHandle | None:
        """Get the underlying DeviceHandle for a device."""
        adapter = self._adapters.get(device_id)
        return adapter.handle if adapter else None

    def get_property(self, device_id: str, prop_name: str) -> Any | None:
        """Get a cached property value.

        Note: This returns the last known value from property streaming.
        For the latest value, use adapter.get(prop_name) which is async.
        """
        device_cache = self._property_cache.get(device_id)
        if device_cache is None:
            return None
        return device_cache.get(prop_name)

    def get_properties(self, device_id: str) -> dict[str, Any]:
        """Get all cached properties for a device."""
        return self._property_cache.get(device_id, {}).copy()

    def get_lasers(self) -> dict[str, DeviceHandleQt]:
        """Get all laser device adapters."""
        if self.rig is None:
            return {}
        return {uid: self._adapters[uid] for uid in self.rig.lasers if uid in self._adapters}

    def get_cameras(self) -> dict[str, DeviceHandleQt]:
        """Get all camera device adapters."""
        if self.rig is None:
            return {}
        return {uid: self._adapters[uid] for uid in self.rig.cameras if uid in self._adapters}

    def get_filter_wheels(self) -> dict[str, DeviceHandleQt]:
        """Get all filter wheel device adapters."""
        if self.rig is None:
            return {}
        return {uid: self._adapters[uid] for uid in self.rig.fws if uid in self._adapters}

    def get_stage_axes(self) -> dict[str, DeviceHandleQt]:
        """Get stage axis adapters (x, y, z)."""
        if self.rig is None:
            return {}
        stage_ids = [
            self.rig.config.stage.x,
            self.rig.config.stage.y,
            self.rig.config.stage.z,
        ]
        return {uid: self._adapters[uid] for uid in stage_ids if uid in self._adapters}
