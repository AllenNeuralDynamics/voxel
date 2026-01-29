"""Adapter for bridging pyrig DeviceHandle to Qt signals."""

import logging
from typing import Any

from pyrig.device import PropsResponse
from PySide6.QtCore import QObject, QTimer, Signal

from pyrig import DeviceHandle
from vxlib import fire_and_forget


class DeviceHandleQt(QObject):
    """Bridges a DeviceHandle's async operations to Qt signals.

    This adapter:
    - Subscribes to device property streaming
    - Emits signals when properties change
    - Provides a clean interface for widgets to call device commands

    Usage:
        adapter = DeviceHandleAdapter(handle)
        adapter.properties_changed.connect(self._on_props)
        await adapter.start()

        # In a slot:
        run_async(adapter.call("enable"))
    """

    # Signals
    properties_changed = Signal(object)  # dict[str, Any] - property values
    connected = Signal(bool)  # Connection status change
    fault = Signal(str)  # Error message

    def __init__(self, handle: DeviceHandle, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._handle = handle
        self._started = False
        self.log = logging.getLogger(f"{self.__class__.__name__}[{handle.uid}]")

    @property
    def handle(self) -> DeviceHandle:
        """Access the underlying DeviceHandle."""
        return self._handle

    @property
    def uid(self) -> str:
        """Device unique identifier."""
        return self._handle.uid

    async def start(self) -> None:
        """Start the adapter and subscribe to device property updates."""
        if self._started:
            return

        try:
            # Subscribe to property updates
            await self._handle.on_props_changed(self._on_properties)
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
            iface = await self._handle.interface()
            prop_names = list(iface.properties.keys())
            self.log.debug("Fetching initial properties: %s", prop_names)
            if prop_names:
                props = await self._handle.get_props(*prop_names)
                self.log.debug("Got initial properties: %s", list(props.res.keys()))
                await self._on_properties(props)
        except Exception as e:
            self.log.warning("Failed to fetch initial properties: %s", e, exc_info=True)

    async def stop(self) -> None:
        """Stop the adapter and cleanup."""
        if not self._started:
            return

        try:
            # DeviceHandle cleanup is handled by the rig
            self._started = False
            self.connected.emit(False)
            self.log.info("Adapter stopped")

        except Exception as e:
            self.log.exception("Error stopping adapter")
            self.fault.emit(f"Stop error: {e!r}")

    async def _on_properties(self, props: PropsResponse) -> None:
        """Handle property update from device."""
        # Emit a dict of property name -> value for simpler widget handling
        values = {name: prop.value for name, prop in props.res.items()}
        self.properties_changed.emit(values)

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
            return await self._handle.call(command, *args, **kwargs)
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
        return await self._handle.get_prop_value(property_name)

    async def set(self, property_name: str, value: Any) -> None:
        """Set a property value.

        Args:
            property_name: Property name
            value: New value
        """
        await self._handle.set_prop(property_name, value)

    async def interface(self):
        """Get the device interface (introspection).

        Returns:
            DeviceInterface with properties, commands, etc.
        """
        return await self._handle.interface()

    async def device_type(self) -> str:
        """Get the device type.

        Returns:
            Device type string
        """
        return await self._handle.device_type()
