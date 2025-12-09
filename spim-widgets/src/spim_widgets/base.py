"""Base classes for device widgets using DeviceClient."""

import asyncio
import logging
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from pyrig.device import DeviceClient
from pyrig.device.base import PropsResponse


class DeviceClientAdapter(QObject):
    """Base adapter that bridges DeviceClient async operations to Qt signals.

    This adapter:
    - Manages the DeviceClient lifecycle (start/stop)
    - Subscribes to device property updates
    - Converts async operations to Qt slots/signals
    - Handles errors and emits fault signals
    """

    # Signals
    properties_changed = Signal(object)  # PropsResponse
    connected_changed = Signal(bool)  # Connection status
    fault = Signal(str)  # Error message

    def __init__(self, client: DeviceClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._subscribe_task: asyncio.Task | None = None
        self._connection_task: asyncio.Task | None = None
        self.log = logging.getLogger(f"{self.__class__.__name__}[{client.uid}]")

    @property
    def client(self) -> DeviceClient:
        """Access the underlying DeviceClient."""
        return self._client

    async def start(self) -> None:
        """Start the adapter and subscribe to device updates."""
        try:
            # Device connection is managed by rig node heartbeats
            # If the device client exists, it's available

            self.connected_changed.emit(True)

            # Subscribe to property updates
            await self._client.subscribe("properties", self._on_properties)

            # Start any additional subscriptions
            await self._start_subscriptions()

            self.log.info(f"Adapter started for {self._client.uid}")

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

            self.log.info(f"Adapter stopped for {self._client.uid}")

        except Exception as e:
            self.log.exception("Error stopping adapter")
            self.fault.emit(f"Stop error: {e!r}")

    def _on_properties(self, topic: str, payload: bytes) -> None:
        """Handle property update messages from DeviceService."""
        try:
            props = PropsResponse.model_validate_json(payload.decode())
            self.properties_changed.emit(props)
        except Exception as e:
            self.log.exception("Error parsing properties")
            self.fault.emit(f"Property parse error: {e!r}")

    async def _start_subscriptions(self) -> None:
        """Override to add additional subscriptions beyond properties.

        Example:
            await self._client.subscribe("custom_topic", self._on_custom)
        """

    async def call_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a device command. Override for device-specific implementations."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement call_command()")


class DeviceClientWidget(QWidget):
    """Base widget class for device control using DeviceClient.

    This provides:
    - Integration with DeviceClientAdapter
    - Async initialization in Qt event loop
    - Cleanup on widget destruction
    - Common UI patterns
    """

    def __init__(self, client: DeviceClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._adapter = self._create_adapter(client)
        self._started = False
        self.log = logging.getLogger(f"{self.__class__.__name__}[{client.uid}]")

        # Connect common signals
        self._adapter.fault.connect(self._on_fault)
        self._adapter.connected_changed.connect(self._on_connection_changed)
        self._adapter.properties_changed.connect(self._on_properties_changed)

        # Setup UI
        self._setup_ui()

    def _create_adapter(self, client: DeviceClient) -> DeviceClientAdapter:
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
            self.log.info(f"Device {self._client.uid} connected")
        else:
            self.log.warning(f"Device {self._client.uid} disconnected")

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
    def client(self) -> DeviceClient:
        """Access the underlying DeviceClient."""
        return self._client

    @property
    def adapter(self) -> DeviceClientAdapter:
        """Access the adapter."""
        return self._adapter
