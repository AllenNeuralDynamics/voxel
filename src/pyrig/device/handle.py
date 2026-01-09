"""User-facing device handle."""

from typing import Any

from .adapter import Adapter
from .agent import StreamCallback
from .base import CommandResponse, Device, DeviceInterface, PropsCallback, PropsResponse
from .props import PropertyModel


class DeviceHandle[D: Device]:
    """User-facing async API for device access. Works with local or remote adapters."""

    def __init__(self, adapter: Adapter[D]):
        self._adapter = adapter
        self._interface: DeviceInterface | None = None

    @property
    def uid(self) -> str:
        return self._adapter.uid

    async def device_type(self) -> str:
        """Get device type, fetching interface if needed."""
        if self._interface is None:
            self._interface = await self._adapter.interface()
        return self._interface.type

    @property
    def device(self) -> D | None:
        """Raw device if local, None if remote."""
        return self._adapter.device

    async def call(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a command and return the result, raising on error."""
        response = await self._adapter.run_command(command, *args, **kwargs)
        return response.unwrap()

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> CommandResponse:
        """Execute a command and return CommandResponse."""
        return await self._adapter.run_command(command, *args, **kwargs)

    async def get_prop_value(self, prop_name: str) -> Any:
        """Get a single property value."""
        prop = await self.get_prop(prop_name)
        return prop.value

    async def get_prop(self, prop_name: str) -> PropertyModel:
        """Get a single property as PropertyModel."""
        props = await self._adapter.get_props(prop_name)
        if prop_name in props.err:
            raise RuntimeError(f"Failed to get {prop_name}: {props.err[prop_name].msg}")
        return props.res[prop_name]

    async def set_prop(self, prop_name: str, value: Any) -> None:
        """Set a single property value."""
        props = await self._adapter.set_props(**{prop_name: value})
        if prop_name in props.err:
            raise RuntimeError(f"Failed to set {prop_name}: {props.err[prop_name].msg}")

    async def get_props(self, *props: str) -> PropsResponse:
        return await self._adapter.get_props(*props)

    async def set_props(self, **props: Any) -> PropsResponse:
        return await self._adapter.set_props(**props)

    async def interface(self) -> DeviceInterface:
        if self._interface is None:
            self._interface = await self._adapter.interface()
        return self._interface

    async def on_props_changed(self, callback: PropsCallback) -> None:
        """Register callback for property change notifications."""
        await self._adapter.on_props_changed(callback)

    async def subscribe(self, topic: str, callback: StreamCallback) -> None:
        await self._adapter.subscribe(topic, callback)

    async def close(self) -> None:
        await self._adapter.close()
