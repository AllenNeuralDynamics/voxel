"""User-facing device handle."""

from abc import ABC, abstractmethod
from typing import Any, Self

from vxlib import Signal

from .driver import Device, StreamCallback
from .props import PropertyModel
from .schema import CommandRequest, DeviceInterface, PropResults, Result, Results


class Adapter[D: Device](ABC):
    """Abstract base for device communication. Used by DeviceHandle."""

    @property
    @abstractmethod
    def uid(self) -> str: ...

    @property
    @abstractmethod
    def device(self) -> D | None: ...

    @property
    @abstractmethod
    def props_changed(self) -> Signal[PropResults]: ...

    @abstractmethod
    async def interface(self) -> DeviceInterface: ...

    @abstractmethod
    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> Result: ...

    @abstractmethod
    async def run_commands(self, commands: list[CommandRequest]) -> Results: ...

    @abstractmethod
    async def get_props(self, *props: str) -> PropResults: ...

    @abstractmethod
    async def set_props(self, **props: Any) -> PropResults: ...

    @abstractmethod
    async def subscribe(self, topic: str, callback: StreamCallback) -> None: ...

    @abstractmethod
    async def unsubscribe(self, topic: str, callback: StreamCallback) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class DeviceHandle[D: Device]:
    """User-facing async API for device access. Works with local or remote adapters.

    Subclass to add typed convenience methods for specific device kinds::

        class CameraHandle(DeviceHandle):
            async def start_preview(self) -> None:
                await self.call("start_preview")


        camera = CameraHandle.wrap(raw_handle)
    """

    def __init__(self, adapter: Adapter[D]):
        self._adapter = adapter
        self._interface: DeviceInterface | None = None

    @property
    def adapter(self) -> Adapter[D]:
        return self._adapter

    @classmethod
    def wrap(cls, handle: "DeviceHandle") -> Self:
        """Create a typed handle sharing another handle's adapter."""
        return cls(handle.adapter)

    @property
    def uid(self) -> str:
        return self._adapter.uid

    @property
    def props_changed(self) -> Signal[PropResults]:
        """Fires on property changes for ``stream=True`` props. Subscribe to receive ``PropResults``."""
        return self._adapter.props_changed

    async def call(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a command and return the result, raising on error."""
        response = await self._adapter.run_command(command, *args, **kwargs)
        return response.unwrap()

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> Result:
        """Execute a command and return CommandResponse."""
        return await self._adapter.run_command(command, *args, **kwargs)

    async def run_commands(self, commands: list[CommandRequest]) -> Results:
        """Execute multiple commands and return batch result."""
        return await self._adapter.run_commands(commands)

    async def get_prop_value(self, prop_name: str) -> Any:
        """Get a single property value."""
        prop = await self.get_prop(prop_name)
        return prop.value

    async def get_prop(self, prop_name: str) -> PropertyModel:
        """Get a single property as PropertyModel."""
        props = await self._adapter.get_props(prop_name)
        return props[prop_name].unwrap()

    async def set_prop(self, prop_name: str, value: Any) -> None:
        """Set a single property value."""
        props = await self._adapter.set_props(**{prop_name: value})
        props[prop_name].unwrap()

    async def get_props(self, *props: str) -> PropResults:
        return await self._adapter.get_props(*props)

    async def set_props(self, **props: Any) -> PropResults:
        return await self._adapter.set_props(**props)

    async def interface(self) -> DeviceInterface:
        if self._interface is None:
            self._interface = await self._adapter.interface()
        return self._interface

    async def subscribe(self, topic: str, callback: StreamCallback) -> None:
        await self._adapter.subscribe(topic, callback)

    async def unsubscribe(self, topic: str, callback: StreamCallback) -> None:
        await self._adapter.unsubscribe(topic, callback)

    async def close(self) -> None:
        await self._adapter.close()
