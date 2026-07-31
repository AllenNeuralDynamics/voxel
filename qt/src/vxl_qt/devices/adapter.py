"""Qt adapters for the active instrument's controlled device API."""

import logging
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from rigup import DeviceInterface, PropertyModel, PropResults
from vxl.instrument import Instrument
from vxlib import Teardown, fire_and_forget

log = logging.getLogger(__name__)


class DeviceHandleQt(QObject):
    """Bridges one instrument-owned device to Qt signals.

    This adapter:
    - Subscribes to device property streaming
    - Emits signals when properties change
    - Provides a clean interface for widgets to call device commands

    Usage:
        adapter = DeviceHandleQt(instrument, interface)
        adapter.properties_changed.connect(self._on_props)
        await adapter.start()

        # In a slot:
        run_async(adapter.call("enable"))
    """

    # Signals
    properties_changed = Signal(object)  # dict[str, Any] - property values
    connected = Signal(bool)  # Connection status change
    fault = Signal(str)  # Error message

    def __init__(self, instrument: Instrument, interface: DeviceInterface, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._instrument = instrument
        self._interface = interface
        self._uid = interface.uid
        self._unsubscribe: Teardown | None = None
        self._started = False
        self._models: dict[str, PropertyModel] = {}  # latest full model per property (value + options/bounds)
        self.log = logging.getLogger(f"{self.__class__.__name__}[{self._uid}]")

    @property
    def uid(self) -> str:
        """Device unique identifier."""
        return self._uid

    @property
    def kind(self) -> str:
        """Device interface type."""
        return self._interface.type

    async def start(self) -> None:
        """Start the adapter and subscribe to device property updates."""
        if self._started:
            return

        try:
            self._unsubscribe = self._instrument.device_property_updates.subscribe(self._on_device_properties)
            self._started = True
            self.connected.emit(True)
            self.log.info("Adapter started")

        except Exception as e:
            self.log.exception("Error starting adapter")
            self.fault.emit(f"Start error: {e!r}")

    def request_initial_properties(self) -> None:
        """Request initial property values. Call after connecting to properties_changed signal."""
        if not self._started:
            return
        # Use QTimer to ensure this runs after the current event loop iteration
        QTimer.singleShot(0, lambda: fire_and_forget(self._emit_initial_properties(), log=self.log))

    async def _emit_initial_properties(self) -> None:
        """Fetch all properties and emit them to initialize widgets."""
        try:
            prop_names = list(self._interface.properties)
            self.log.debug("Fetching initial properties: %s", prop_names)
            if prop_names:
                props = await self._instrument.get_device_properties(self._uid, prop_names)
                self.log.debug("Got initial properties: %s", list(props.ok.keys()))
                await self._on_properties(props)
        except Exception as e:
            self.log.warning("Failed to fetch initial properties: %s", e, exc_info=True)

    async def stop(self) -> None:
        """Stop the adapter and cleanup."""
        if not self._started:
            return

        try:
            if self._unsubscribe is not None:
                self._unsubscribe()
                self._unsubscribe = None
            self._started = False
            self.connected.emit(False)
            self.log.info("Adapter stopped")

        except Exception as e:
            self.log.exception("Error stopping adapter")
            self.fault.emit(f"Stop error: {e!r}")

    async def _on_properties(self, props: PropResults) -> None:
        """Cache the full property models (value + options/bounds), then emit bare values to widgets."""
        self._models.update(props.ok)
        self.properties_changed.emit({name: model.value for name, model in props.ok.items()})

    async def _on_device_properties(self, update: tuple[str, PropResults]) -> None:
        """Forward property updates for this adapter's device."""
        device_id, props = update
        if device_id == self._uid:
            await self._on_properties(props)

    def model(self, name: str) -> PropertyModel | None:
        """Latest full model for ``name`` — its value plus any enumerated options / numeric bounds."""
        return self._models.get(name)

    async def call(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a device command.

        Args:
            command: Command name
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Command result

        Raises:
            Exception: If command fails
        """
        try:
            result = await self._instrument.execute_device_command(self._uid, command, args, kwargs)
            return result.unwrap()
        except Exception as e:
            self.log.exception(f"Command {command} failed")
            self.fault.emit(f"Command {command} failed: {e}")
            raise

    async def get(self, property_name: str) -> Any:
        """Get a property value.

        Args:
            property_name: Property name

        Returns:
            Property value
        """
        props = await self._instrument.get_device_properties(self._uid, [property_name])
        await self._on_properties(props)
        return props[property_name].unwrap().value

    async def set(self, property_name: str, value: Any) -> None:
        """Set a property value.

        Args:
            property_name: Property name
            value: New value
        """
        results = await self._instrument.set_device_properties(self._uid, {property_name: value})
        results.unwrap()

    async def interface(self) -> DeviceInterface:
        """Get the device interface (introspection).

        Returns:
            DeviceInterface with properties, commands, etc.
        """
        return self._interface

    async def device_type(self) -> str:
        """Get the device type.

        Returns:
            Device type string
        """
        return self._interface.type


class DevicesStore(QObject):
    """Manages device handles and their Qt adapters for the UI.

    Creates a :class:`DeviceHandleQt` adapter for every device exposed by the instrument and provides
    access methods for widgets to query device state and subscribe to property updates.

    Usage:
        store = DevicesStore()
        await store.start(instrument)

        adapter = store.get_adapter("laser_488")
        adapter.properties_changed.connect(self._on_laser_props)

        value = store.get_property("laser_488", "power")
    """

    device_added = Signal(str)  # device_id
    device_removed = Signal(str)  # device_id
    ready = Signal()  # All adapters started

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._instrument: Instrument | None = None
        self._adapters: dict[str, DeviceHandleQt] = {}
        self._started = False
        self._property_cache: dict[str, dict[str, Any]] = {}

    @property
    def adapters(self) -> dict[str, DeviceHandleQt]:
        """All device adapters by device ID."""
        return self._adapters

    async def start(self, instrument: Instrument) -> None:
        """Inspect the instrument and create adapters for its available devices."""
        if self._started:
            log.warning("DevicesStore already started")
            return

        self._instrument = instrument
        snapshots = await instrument.inspect_devices()
        log.info("Starting DevicesStore with %d devices", len(snapshots))

        for uid, snapshot in snapshots.items():
            if snapshot.interface is None:
                log.warning("Skipping unavailable device %s: %s", uid, snapshot.error)
                continue
            adapter = DeviceHandleQt(instrument, snapshot.interface, parent=self)
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
        self._instrument = None
        self._started = False

    def _on_properties(self, device_id: str, props: dict[str, Any]) -> None:
        """Handle property update from an adapter."""
        if device_id in self._property_cache:
            self._property_cache[device_id].update(props)

    def get_adapter(self, device_id: str) -> DeviceHandleQt | None:
        """Get the Qt adapter for a device."""
        return self._adapters.get(device_id)

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
        return {uid: adapter for uid, adapter in self._adapters.items() if adapter.kind == "laser"}

    def get_cameras(self) -> dict[str, DeviceHandleQt]:
        """Get all camera device adapters."""
        return {uid: adapter for uid, adapter in self._adapters.items() if adapter.kind == "camera"}

    def get_filter_wheels(self) -> dict[str, DeviceHandleQt]:
        """Get all filter wheel device adapters."""
        if self._instrument is None:
            return {}
        return {
            uid: self._adapters[uid] for uid in self._instrument.hardware_config.filter_wheels if uid in self._adapters
        }

    def get_stage_axes(self) -> dict[str, DeviceHandleQt]:
        """Get stage axis adapters (x, y, z)."""
        if self._instrument is None:
            return {}
        stage = self._instrument.hardware_config.stage
        stage_ids = [stage.x, stage.y, stage.z]
        return {uid: self._adapters[uid] for uid in stage_ids if uid in self._adapters}
