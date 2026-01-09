"""Unified device handle using composition with Transport."""

from typing import Any

from .base import (
    CommandResponse,
    Device,
    DeviceInterface,
    PropsResponse,
)
from .props import PropertyModel
from .transport import LocalTransport, SubscribeCallback, Transport


class DeviceHandle[D: Device]:
    """Unified handle for device access via composition with Transport.

    Works with both local and remote devices - the Transport handles
    the communication details.

    Subclass this to add typed methods for specific device types
    (e.g., CameraHandle, DaqHandle).
    """

    def __init__(self, transport: Transport[D]):
        self._transport = transport

    @property
    def uid(self) -> str:
        """Device unique identifier."""
        return self._transport.uid

    @property
    def device_type(self) -> str:
        """Device type identifier."""
        return self._transport.device_type

    @property
    def device(self) -> D | None:
        """Raw device if local, None if remote."""
        return self._transport.device

    @property
    def is_local(self) -> bool:
        """True if this handle wraps a local device."""
        return self._transport.device is not None

    # Command execution

    async def call(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a command and return the result, raising on error."""
        return await self._transport.call(command, *args, **kwargs)

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> CommandResponse:
        """Execute a command and return raw CommandResponse."""
        return await self._transport.run_command(command, *args, **kwargs)

    # Property access - single

    async def get_prop_value(self, prop_name: str) -> Any:
        """Get a single property value, raising on error."""
        return await self._transport.get_prop_value(prop_name)

    async def get_prop(self, prop_name: str) -> PropertyModel:
        """Get a single property as PropertyModel, raising on error."""
        return await self._transport.get_prop(prop_name)

    async def set_prop(self, prop_name: str, value: Any) -> None:
        """Set a single property value, raising on error."""
        return await self._transport.set_prop(prop_name, value)

    # Property access - batch

    async def get_props(self, *props: str) -> PropsResponse:
        """Get multiple property values."""
        return await self._transport.get_props(*props)

    async def set_props(self, **props: Any) -> PropsResponse:
        """Set multiple property values."""
        return await self._transport.set_props(**props)

    # Introspection

    async def get_interface(self) -> DeviceInterface:
        """Get the device interface information."""
        return await self._transport.get_interface()

    # Subscriptions

    async def subscribe(self, topic: str, callback: SubscribeCallback) -> None:
        """Subscribe to device updates.

        Args:
            topic: Topic to subscribe to (e.g., "properties")
            callback: Async function receiving (topic, PropsResponse)
        """
        await self._transport.subscribe(topic, callback)

    # Lifecycle

    async def close(self) -> None:
        """Release resources associated with this handle."""
        await self._transport.close()


def local_handle[D: Device](device: D) -> DeviceHandle[D]:
    """Create a DeviceHandle for a local device."""
    return DeviceHandle(LocalTransport(device))
