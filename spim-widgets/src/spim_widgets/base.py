"""Base classes for device widgets using DeviceHandle."""

import asyncio
import logging
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from pyrig import DeviceHandle
from pyrig.device import PropsResponse


class RemoteHandleAdapter(QObject):
    """Base adapter that bridges DeviceHandle async operations to Qt signals.

    This adapter:
    - Manages the DeviceHandle lifecycle (start/stop)
    - Subscribes to device property updates
    - Converts async operations to Qt slots/signals
    - Handles errors and emits fault signals
    """

    # Signals
    properties_changed = Signal(object)  # PropsResponse
    connected_changed = Signal(bool)  # Connection status
    fault = Signal(str)  # Error message

    def __init__(self, handle: DeviceHandle, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._handle = handle
        self._subscribe_task: asyncio.Task | None = None
        self._connection_task: asyncio.Task | None = None
        self.log = logging.getLogger(f"{self.__class__.__name__}[{handle.uid}]")

    @property
    def handle(self) -> DeviceHandle:
        """Access the underlying DeviceHandle."""
        return self._handle

    async def start(self) -> None:
        """Start the adapter and subscribe to device updates."""
        try:
            # Device connection is managed by rig node heartbeats
            # If the device handle exists, it's available

            self.connected_changed.emit(True)

            # Subscribe to property updates
            await self._handle.on_props_changed(self._on_properties)

            # Start any additional subscriptions
            await self._start_subscriptions()

            self.log.info(f"Adapter started for {self._handle.uid}")

        except Exception as e:
            self.log.exception("Error starting adapter")
            self.fault.emit(f"Start error: {e!r}")

    async def stop(self) -> None:
        """Stop the adapter and cleanup."""
        try:
            if self._subscribe_task and not self._subscribe_task.done():
                self._subscribe_task.cancel()
                try:
                    await self._subscribe_task
                except asyncio.CancelledError:
                    pass

            if self._connection_task and not self._connection_task.done():
                self._connection_task.cancel()
                try:
                    await self._connection_task
                except asyncio.CancelledError:
                    pass

            self.log.info(f"Adapter stopped for {self._handle.uid}")

        except Exception as e:
            self.log.exception("Error stopping adapter")
            self.fault.emit(f"Stop error: {e!r}")

    async def _on_properties(self, props: PropsResponse) -> None:
        """Handle property update messages from device."""
        self.properties_changed.emit(props)

    async def _start_subscriptions(self) -> None:
        """Override to add additional subscriptions beyond properties.

        Example:
            await self._handle.subscribe("custom_topic", self._on_custom)
        """

    async def call_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a device command. Override for device-specific implementations."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement call_command()")


class RemoteHandleWidget(QWidget):
    """Base widget class for device control using DeviceHandle.

    This provides:
    - Integration with RemoteHandleAdapter
    - Async initialization in Qt event loop
    - Cleanup on widget destruction
    - Common UI patterns
    """

    def __init__(self, handle: DeviceHandle, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._handle = handle
        self._adapter = self._create_adapter(handle)
        self._started = False
        self.log = logging.getLogger(f"{self.__class__.__name__}[{handle.uid}]")

        # Connect common signals
        self._adapter.fault.connect(self._on_fault)
        self._adapter.connected_changed.connect(self._on_connection_changed)
        self._adapter.properties_changed.connect(self._on_properties_changed)

        # Setup UI
        self._setup_ui()

    def _create_adapter(self, handle: DeviceHandle) -> RemoteHandleAdapter:
        """Create the device-specific adapter. Must be implemented by subclasses."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement _create_adapter()")

    def _setup_ui(self) -> None:
        """Setup the UI. Must be implemented by subclasses."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement _setup_ui()")

    def _on_properties_changed(self, props: PropsResponse) -> None:
        """Handle property updates. Must be implemented by subclasses."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement _on_properties_changed()")

    def _on_connection_changed(self, connected: bool) -> None:
        """Handle connection status changes. Override to customize."""
        if connected:
            self.log.info(f"Device {self._handle.uid} connected")
        else:
            self.log.warning(f"Device {self._handle.uid} disconnected")

    def _on_fault(self, error: str) -> None:
        """Handle faults. Override to customize."""
        self.log.error(f"Fault: {error}")

    async def start(self) -> None:
        """Start the widget's adapter."""
        if not self._started:
            await self._adapter.start()
            self._started = True

    async def stop(self) -> None:
        """Stop the widget's adapter."""
        if self._started:
            await self._adapter.stop()
            self._started = False

    def closeEvent(self, event) -> None:
        """Handle widget close event - cleanup adapter."""
        if self._started:
            # Schedule cleanup in async context
            asyncio.create_task(self.stop())
        super().closeEvent(event)

    @property
    def handle(self) -> DeviceHandle:
        """Access the underlying DeviceHandle."""
        return self._handle

    @property
    def adapter(self) -> RemoteHandleAdapter:
        """Access the adapter."""
        return self._adapter
