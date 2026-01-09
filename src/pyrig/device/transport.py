"""Transport abstraction for local device communication."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .base import (
    CommandResponse,
    Device,
    DeviceInterface,
    PropsResponse,
)
from .executor import DeviceExecutor
from .props import PropertyModel

# Type alias for subscribe callbacks - receives topic and parsed PropsResponse
SubscribeCallback = Callable[[str, PropsResponse], Awaitable[None]]


class Transport[D: Device](Protocol):
    """Protocol for device communication transport (local or remote)."""

    @property
    def uid(self) -> str:
        """Device unique identifier."""
        ...

    @property
    def device_type(self) -> str:
        """Device type identifier."""
        ...

    @property
    def device(self) -> D | None:
        """Raw device if local, None if remote."""
        ...

    async def call(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a command and return the result, raising on error."""
        ...

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> CommandResponse:
        """Execute a command and return raw CommandResponse."""
        ...

    async def get_prop_value(self, prop_name: str) -> Any:
        """Get a single property value."""
        ...

    async def get_prop(self, prop_name: str) -> PropertyModel:
        """Get a single property as PropertyModel."""
        ...

    async def set_prop(self, prop_name: str, value: Any) -> None:
        """Set a single property value."""
        ...

    async def get_props(self, *props: str) -> PropsResponse:
        """Get multiple property values."""
        ...

    async def set_props(self, **props: Any) -> PropsResponse:
        """Set multiple property values."""
        ...

    async def get_interface(self) -> DeviceInterface:
        """Get the device interface information."""
        ...

    async def subscribe(self, topic: str, callback: SubscribeCallback) -> None:
        """Subscribe to device updates.

        Args:
            topic: Topic to subscribe to (e.g., "properties")
            callback: Async function receiving (topic, PropsResponse)
        """
        ...

    async def close(self) -> None:
        """Release resources."""
        ...


class LocalTransport[D: Device]:
    """Transport for local device access, wrapping DeviceExecutor."""

    def __init__(self, device: D):
        self._executor = DeviceExecutor(device)

    @property
    def uid(self) -> str:
        return self._executor.uid

    @property
    def device_type(self) -> str:
        return self._executor.device.__DEVICE_TYPE__

    @property
    def device(self) -> D:
        return self._executor.device

    @property
    def interface(self) -> DeviceInterface:
        return self._executor.interface

    async def call(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a command and return the result, raising on error."""
        response = await self.run_command(command, *args, **kwargs)
        return response.unwrap()

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> CommandResponse:
        """Execute a command and return CommandResponse."""
        return await self._executor.execute_command(command, *args, **kwargs)

    async def get_prop_value(self, prop_name: str) -> Any:
        """Get a single property value."""
        prop = await self.get_prop(prop_name)
        return prop.value

    async def get_prop(self, prop_name: str) -> PropertyModel:
        """Get a single property as PropertyModel."""
        props = await self.get_props(prop_name)
        if prop_name in props.err:
            raise RuntimeError(f"Failed to get {prop_name}: {props.err[prop_name].msg}")
        return props.res[prop_name]

    async def set_prop(self, prop_name: str, value: Any) -> None:
        """Set a single property value."""
        props = await self.set_props(**{prop_name: value})
        if prop_name in props.err:
            raise RuntimeError(f"Failed to set {prop_name}: {props.err[prop_name].msg}")

    async def get_props(self, *props: str) -> PropsResponse:
        """Get property values."""
        return await self._executor.get_props(*props)

    async def set_props(self, **props: Any) -> PropsResponse:
        """Set property values."""
        return await self._executor.set_props(**props)

    async def get_interface(self) -> DeviceInterface:
        """Return the pre-collected interface."""
        return self._executor.interface

    async def subscribe(self, topic: str, callback: SubscribeCallback) -> None:
        """Subscribe to property updates.

        Args:
            topic: Topic to subscribe to (currently only "properties" is supported)
            callback: Async function receiving (topic, PropsResponse)
        """
        if topic != "properties":
            raise ValueError(f"LocalTransport only supports 'properties' topic, got: {topic}")

        # Wrap callback to include the topic
        full_topic = f"{self.uid}/properties"

        async def wrapped_callback(props: PropsResponse) -> None:
            await callback(full_topic, props)

        self._executor.subscribe_to_stream(wrapped_callback)

    async def close(self) -> None:
        """Shutdown the executor."""
        self._executor.close_executor()
